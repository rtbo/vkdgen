#! /usr/bin/env python3
"""
    Vulkan D bindings generator.
    Reads Vulkan XML API definition to produce the D bindings code.
    Also depends on the python scripts from Vulkan-Headers.
"""

from generator import OutputGenerator, GeneratorOptions
import re
from itertools import islice

# General utility

# noneStr - returns string argument, or "" if argument is None.
# Used in converting etree Elements into text.
#   str - string to convert
def noneStr(str):
    if (str):
        return str
    else:
        return ""

# SourceFile: gather and format the source code in the different sections
# and issue them into a file
class SourceFile(object):
    '''
    buffer to append code in various sections of a file
    in any order
    '''

    _one_indent_level = '    '

    def __init__(self):
        self._lines = []
        self._indent = 0


    def indentBlock(self):
        class Indenter(object):
            def __init__(self, sf):
                self.sf = sf
            def __enter__(self):
                self.sf.indent()
            def __exit__(self, type, value, traceback):
                self.sf.unindent()
        return Indenter(self)

    def indent(self):
        '''
        adds one level of indentation to the current section
        '''
        self._indent += 1

    def unindent(self):
        '''
        removes one level of indentation to the current section
        '''
        self._indent -= 1

    def __call__(self, fmt="", *args):
        '''
        Append a line to the file at in its current section and
        indentation of the current section
        '''
        indent = SourceFile._one_indent_level * self._indent
        self._lines.append(indent + (fmt % args))


    def writeOut(self, outFile):
        for line in self._lines:
            print(line.rstrip(), file=outFile)


# D specific utilities

re_single_const = re.compile(r"^const\s+(.+)\*\s*$")
re_double_const = re.compile(r"^const\s+(.+)\*\s+const\*\s*$")
re_funcptr = re.compile(r"^typedef (.+) \(VKAPI_PTR \*$")

dkeywords = [ "module" ]

def convertDTypeConst( typ ):
    """
    Converts C const syntax to D const syntax
    """
    doubleConstMatch = re.match( re_double_const, typ )
    if doubleConstMatch:
        return "const({}*)*".format( doubleConstMatch.group( 1 ))
    else:
        singleConstMatch = re.match( re_single_const, typ )
        if singleConstMatch:
            return "const({})*".format( singleConstMatch.group( 1 ))
    return typ

def makeDParamType(param):
    def makePart(part):
        return noneStr(part).replace("struct ", "").strip().replace("const", "const ")

    typeStr = makePart(param.text)
    for elem in param:
        if elem.tag != "name":
            typeStr += makePart(elem.text)
        typeStr += makePart(elem.tail)

    return convertDTypeConst(typeStr.replace("const *", "const*"))

def mapDName(name):
    if name in dkeywords:
        return name + "_"
    return name



class DGeneratorOptions(GeneratorOptions):

    from generator import regSortFeatures

    def __init__(self,
                 filename = None,
                 directory = '.',
                 apiname = None,
                 profile = None,
                 versions = '.*',
                 emitversions = '.*',
                 defaultExtensions = None,
                 addExtensions = None,
                 removeExtensions = None,
                 emitExtensions = None,
                 sortProcedure = regSortFeatures,
                 regFile = '',
                 module = ''):
        GeneratorOptions.__init__(self, filename, directory, apiname, profile,
                                  versions, emitversions, defaultExtensions,
                                  addExtensions, removeExtensions,
                                  emitExtensions, sortProcedure)
        self.regFile = regFile
        self.module = module


class DGenerator(OutputGenerator):

    class FeatureGuard:
        def __init__(self, versionGuards, stmts):
            self.name = ""
            self.versionGuards = versionGuards
            self.stmts = stmts

        def begin(self, sf):
            for vg in self.versionGuards:
                sf("version(%s) {", vg)
                sf.indent()

        def end(self, sf):
            for vg in self.versionGuards:
                sf.unindent()
                sf("}")

    class BaseType:
        def __init__(self, name, alias):
            self.name = name
            self.alias = alias

    class Const:
        def __init__(self, name, value):
            self.name = name
            self.value = value

    class Enum:
        def __init__(self, name, members, values):
            assert len(members) == len(values)
            self.name = name
            self.members = members
            self.values = values

    # Param is both struct member and command param
    class Param:
        def __init__(self, name, typeStr):
            self.name = name
            self.typeStr = typeStr

    class Struct:
        def __init__(self, name, category, params):
            self.name = name
            self.category = category
            self.params = params

    class Command:
        def __init__(self, name, ret, params):
            self.name = name
            self.returnType = ret
            self.params = params

    class Feature:
        def __init__(self, name, guard):
            self.name = name
            self.guard = guard
            self.baseTypes = []
            self.handles = []
            self.ndHandles = []
            self.consts = []
            self.funcptrs = []
            self.enums = []
            self.structs = []
            self.cmds = []
            self.instanceCmds = []
            self.deviceCmds = []

        def beginGuard(self, sf):
            if self.guard != None:
                self.guard.begin(sf)

        def endGuard(self, sf):
            if self.guard != None:
                self.guard.end(sf)

    def __init__(self):
        super().__init__()
        self.headerVersion = ""
        self.basicTypes = {
            "uint8_t": "ubyte",
            "uint16_t": "ushort",
            "uint32_t": "uint",
            "uint64_t": "ulong",
            "int8_t": "byte",
            "int16_t": "short",
            "int32_t": "int",
            "int64_t": "long",
        }

        self.globalCmdNames = {
            "vkGetInstanceProcAddr",
            "vkEnumerateInstanceExtensionProperties",
            "vkEnumerateInstanceLayerProperties",
            "vkCreateInstance"
        }
        self.globalCmds = []

        self.features = []
        self.feature = None
        self.featureGuards = {
            "VK_KHR_win32_surface": DGenerator.FeatureGuard(
                ["Windows"],
                [ "import core.sys.windows.windef : HINSTANCE, HWND;" ]
            ),
            "VK_KHR_xcb_surface": DGenerator.FeatureGuard(
                ["linux", "VkXcb"],
                [ "import xcb.xcb : xcb_connection_t, xcb_visualid_t, xcb_window_t;" ]
            ),
            "VK_KHR_wayland_surface": DGenerator.FeatureGuard(
                ["linux", "VkWayland"],
                [
                    "import wayland.native.client : wl_display, wl_proxy;",
                    "alias wl_surface = wl_proxy;"
                ]
            )
        }
        for k in self.featureGuards:
            self.featureGuards[k].name = k

    def logMsg(self, level, *args):
        # shut down logging during dev to see debug output
        # super().logMsg(level, *args)
        pass

    def beginFile(self, opts):
        self.opts = opts
        # generator base class open and close a file
        # don't want that here as we may output to stdout
        # not calling super on purpose

        # Everything is written in endFile
        pass

    def endFile(self):
        # not calling super on purpose (see beginFile comment)
        sf = SourceFile()
        sf("/// Vulkan D bindings generated automatically by vkdgen")
        sf("/// See https://github.com/rtbo/vkdgen")
        sf("module %s;", self.opts.module)
        sf()
        for k in self.featureGuards:
            fg = self.featureGuards[k]
            fg.begin(sf)
            for s in fg.stmts:
                sf(s)
            fg.end(sf)
            sf()

        if self.headerVersion != "":
            sf("enum VK_HEADER_VERSION = %s;", self.headerVersion)

        self.issueBaseTypes(sf)
        self.issueHandles(sf)
        self.issueConsts(sf)
        self.issueFuncptrs(sf)
        self.issueEnums(sf)
        self.issueStructs(sf)

        self.issueCmdPtrAliases(sf)
        self.issueGlobalCmds(sf)
        self.issueInstanceCmds(sf)
        self.issueDeviceCmds(sf)

        with open(self.opts.filename, "w") as outFile:
            sf.writeOut(outFile)

    def beginFeature(self, interface, emit):
        super().beginFeature(interface, emit)

        feature = interface.get("name")
        guard = None
        if feature in self.featureGuards:
            guard = self.featureGuards[feature]

        self.feature = DGenerator.Feature(feature, guard)


    def endFeature(self):
        super().endFeature()
        self.features.append(self.feature)
        self.feature = None


    def genType(self, typeinfo, name, alias):
        super().genType(typeinfo, name, alias)

        if alias:
            # fixme
            return

        if "category" not in typeinfo.elem.attrib:
            return
        category = typeinfo.elem.attrib["category"]

        if category == "basetype" or category == "bitmask":
            self.feature.baseTypes.append(
                DGenerator.BaseType(name, typeinfo.elem.find("type").text)
            )

        elif category == "handle":
            handleType = typeinfo.elem.find("type").text
            if handleType == "VK_DEFINE_HANDLE":
                self.feature.handles.append(name)
            else:
                assert handleType == "VK_DEFINE_NON_DISPATCHABLE_HANDLE"
                self.feature.ndHandles.append(name)

        elif category == "struct" or category == "union":
            self.genStruct(typeinfo, name, alias)

        elif category == 'define' and name == 'VK_HEADER_VERSION':
            for headerVersion in islice( typeinfo.elem.itertext(), 2, 3 ):	# get the version string from the one element list
                self.headerVersion = headerVersion
                break

        elif category == "funcpointer":

            returnType = re.match( re_funcptr, typeinfo.elem.text ).group( 1 )

            paramsTxt = "".join( islice( typeinfo.elem.itertext(), 2, None ))[ 2: ]
            params = []

            if paramsTxt != "void);" and paramsTxt != " void );":
                for line in paramsTxt.splitlines():
                    lineSplit = line.split()
                    if len(lineSplit) == 0:
                        continue
                    if len(lineSplit) == 3 and lineSplit[0] == "const":
                        typeStr = "const(" + lineSplit[1] + ")"
                        typeStr = typeStr.replace("*)", ")*")
                        paramName = lineSplit[2]
                    else:
                        assert len(lineSplit) == 2
                        typeStr = lineSplit[0]
                        paramName = lineSplit[1]
                    paramName = paramName.replace(",", "").replace(")", "").replace(";", "")
                    params.append(
                        DGenerator.Param(paramName, typeStr)
                    )

            self.feature.funcptrs.append(
                DGenerator.Command(name, returnType, params)
            )

    # an enum is a single constant
    def genEnum(self, enuminfo, name, alias):
        super().genEnum(enuminfo, name, alias)
        (_, strVal) = self.enumToValue(enuminfo.elem, False)
        if alias:
            print('enum: ', alias)
        self.feature.consts.append(
                DGenerator.Const(
                    name,
                    strVal
                        .replace("0ULL", "0")
                        .replace("0L", "0")
                        .replace("0U", "0")
                        .replace("(", "")
                        .replace(")", "")
            )
        )

    # a group is an enumeration of several related constants
    def genGroup(self, groupinfo, name, alias):
        super().genGroup(groupinfo, name, alias)

        if alias:
            print('group: ', alias)

        members = []
        values = []
        enums = self.checkDuplicateEnums(groupinfo.elem.findall('enum'))
        for elem in enums:
            (numVal, strVal) = self.enumToValue(elem, True)
            members.append(elem.get("name"))
            values.append(strVal)

        self.feature.enums.append(
            DGenerator.Enum(name, members, values)
        )

    def genStruct(self, typeinfo, name, alias):
        super().genStruct(typeinfo, name, alias)
        category = typeinfo.elem.attrib["category"]
        params = []
        for member in typeinfo.elem.findall(".//member"):
            typeStr = makeDParamType(member)
            memName = member.find("name").text
            if memName in dkeywords:
                memName += "_"
            params.append(
                DGenerator.Param(memName, typeStr)
            )

        self.feature.structs.append(
            DGenerator.Struct(name, category, params)
        )

    def genCmd(self, cmdinfo, name, alias):
        super().genCmd(cmdinfo, name, alias)
        typeStr = cmdinfo.elem.findall("./proto/type")[0].text
        params=[]
        for pElem in cmdinfo.elem.findall("./param"):
            p = DGenerator.Param(pElem.find("name").text, makeDParamType(pElem))
            params.append(p)

        cmd = DGenerator.Command(name, typeStr, params)

        self.feature.cmds.append(cmd)

        if name in self.globalCmdNames:
            self.globalCmds.append(cmd)
        elif name != "vkGetDeviceProcAddr" and len(params) and params[0].typeStr in { "VkDevice", "VkQueue", "VkCommandBuffer" }:
            self.feature.deviceCmds.append(cmd)
        else:
            self.feature.instanceCmds.append(cmd)

    def issueBaseTypes(self, sf):
        sf()
        sf("// Basic types definition")
        sf()
        maxLen = 0
        for bt in self.basicTypes:
            maxLen = max(maxLen, len(bt))
        for bt in self.basicTypes:
            spacer = " " * (maxLen - len(bt))
            sf("alias %s%s = %s;", bt, spacer, self.basicTypes[bt])
        for f in [f for f in self.features if len(f.baseTypes) > 0]:
            sf()
            sf("// %s", f.name)
            f.beginGuard(sf)
            maxLen = 0
            for bt in f.baseTypes:
                maxLen = max(maxLen, len(bt.name))
            for bt in f.baseTypes:
                spacer = " " * (maxLen - len(bt.name))
                sf("alias %s%s = %s;", bt.name, spacer, bt.alias)
            f.endGuard(sf)

    def issueHandles(self, sf):
        sf()
        sf("// Handles")
        sf()
        feats = [f for f in self.features if len(f.handles) > 0]
        for i, f in enumerate(feats):
            if i != 0:
                sf()
            sf("// %s", f.name)
            f.beginGuard(sf)
            maxLen = 0
            for h in f.handles:
                maxLen = max(maxLen, len(h))
            for h in f.handles:
                spacer = " " * (maxLen - len(h))
                sf("struct %s_T; %salias %s %s= %s_T*;", h, spacer, h, spacer, h)
            f.endGuard(sf)

        sf()
        sf("// Non-dispatchable handles")
        sf()
        feats = [f for f in self.features if len(f.ndHandles) > 0]
        sf("version(X86_64) {")
        with sf.indentBlock():
            for i, f in enumerate(feats):
                if i != 0:
                    sf()
                sf("// %s", f.name)
                f.beginGuard(sf)
                maxLen = 0
                for h in f.ndHandles:
                    maxLen = max(maxLen, len(h))
                for h in f.ndHandles:
                    spacer = " " * (maxLen - len(h))
                    sf("struct %s_T; %salias %s %s= %s_T*;", h, spacer, h, spacer, h)
                f.endGuard(sf)
        sf("}")
        sf("else {")
        with sf.indentBlock():
            for i, f in enumerate(feats):
                if i != 0:
                    sf()
                sf("// %s", f.name)
                f.beginGuard(sf)
                maxLen = 0
                for h in f.ndHandles:
                    maxLen = max(maxLen, len(h))
                for h in f.ndHandles:
                    spacer = " " * (maxLen - len(h))
                    sf('alias %s %s= ulong;', h, spacer)
                f.endGuard(sf)
        sf("}")

    def issueFuncptrs(self, sf):
        sf()
        sf("// Function pointers")
        sf()
        sf("extern(C) nothrow {")
        with sf.indentBlock():
            feats = [f for f in self.features if len(f.funcptrs) > 0]
            for i, f in enumerate(feats):
                if i != 0: sf()
                sf("// %s", f.name)
                f.beginGuard(sf)
                for fp in f.funcptrs:
                    if not len(fp.params):
                        sf("alias %s = %s function();", fp.name, fp.returnType)
                    else:
                        maxLen = 0
                        for p in fp.params:
                            maxLen = max(maxLen, len(p.typeStr))
                        sf("alias %s = %s function(", fp.name, fp.returnType)
                        with sf.indentBlock():
                            for i, p in enumerate(fp.params):
                                spacer = " " * (maxLen - len(p.typeStr))
                                endLine = "" if i == len(fp.params)-1 else ","
                                sf("%s%s %s%s", p.typeStr, spacer, p.name, endLine)
                        sf(");")
                f.endGuard(sf)
        sf("}")

    def issueConsts(self, sf):
        sf()
        sf("// Constants")
        for f in [f for f in self.features if len(f.consts) > 0]:
            sf()
            sf("// %s", f.name)
            f.beginGuard(sf)
            maxLen = 0
            for c in f.consts:
                maxLen = max(maxLen, len(c.name))
            for c in f.consts:
                spacer = " " * (maxLen - len(c.name))
                sf("enum %s%s = %s;", c.name, spacer, c.value)
            f.endGuard(sf)

    def issueEnums(self, sf):
        sf()
        sf("// Enumerations")
        for f in [f for f in self.features if len(f.enums) > 0]:
            sf()
            sf("// %s", f.name)
            f.beginGuard(sf)
            for e in f.enums:
                repStr = ""
                if e.name.endswith("FlagBits"):
                    repStr = " : VkFlags"

                maxLen = 0
                for m in e.members:
                    maxLen = max(maxLen, len(m))

                sf("enum %s%s {", e.name, repStr)
                with sf.indentBlock():
                    for i in range(len(e.members)):
                        spacer = " " * (maxLen - len(e.members[i]))
                        sf("%s%s = %s,", e.members[i], spacer, e.values[i])
                sf("}")
                for m in e.members:
                    spacer = " " * (maxLen - len(m))
                    sf("enum %s%s = %s.%s;", m, spacer, e.name, m)
                sf()
            f.endGuard(sf)


    def issueStructs(self, sf):
        sf()
        sf("// Structures")
        for f in [f for f in self.features if len(f.structs) > 0]:
            sf()
            sf("// %s", f.name)
            f.beginGuard(sf)
            for s in f.structs:
                maxLen = 0
                for p in s.params:
                    maxLen = max(maxLen, len(p.typeStr))
                sf("%s %s {", s.category, s.name)
                with sf.indentBlock():
                    for p in s.params:
                        spacer = " " * (maxLen - len(p.typeStr))
                        sf("%s%s %s;", p.typeStr, spacer, p.name)
                sf("}")

            f.endGuard(sf)

    def issueCmdPtrAliases(self, sf):
        sf()
        sf("// Command pointer aliases")
        sf()
        sf("extern(C) nothrow @nogc {")
        with sf.indentBlock():
            feats = [f for f in self.features if len(f.cmds) > 0]
            for i, f in enumerate(feats):
                if i != 0:
                    sf()
                sf("// %s", f.name)
                f.beginGuard(sf)
                for cmd in f.cmds:
                    maxLen = 0
                    for p in cmd.params:
                        maxLen = max(maxLen, len(p.typeStr))
                    fstLine = "alias PFN_{} = {} function (".format(cmd.name, cmd.returnType)
                    if len(cmd.params) == 0:
                        sf(fstLine+");")
                        continue

                    sf(fstLine)
                    with sf.indentBlock():
                        for p in cmd.params:
                            spacer = " " * (maxLen-len(p.typeStr))
                            sf("%s%s %s,", p.typeStr, spacer, p.name)
                    sf(");")

                f.endGuard(sf)

        sf("}")
        sf()

    def issueGlobalCmds(self, sf):
        maxLen = 0
        for cmd in self.globalCmds:
            maxLen = max(maxLen, len(cmd.name))

        sf()
        sf("// Global commands")
        sf()
        sf("final class VkGlobalCmds {")
        with sf.indentBlock():
            sf()
            sf("this (PFN_vkGetInstanceProcAddr loader) {")
            with sf.indentBlock():
                sf("_GetInstanceProcAddr = loader;")
                for cmd in [cmd for cmd in self.globalCmds if cmd.name != "vkGetInstanceProcAddr"]:
                    spacer = " " * (maxLen - len(cmd.name))
                    membName = cmd.name[2:]
                    sf(
                        "_%s%s = cast(PFN_%s)%sloader(null, \"%s\");",
                        membName, spacer, cmd.name, spacer, cmd.name
                    )
            sf("}")
            for cmd in self.globalCmds:
                spacer = " " * (maxLen - len(cmd.name))
                # vkCmdName => CmdName
                membName = cmd.name[2:]
                paramStr = ", ".join(map((lambda p: "{} {}".format(p.typeStr, p.name)), cmd.params))
                argStr = ", ".join(map((lambda p: p.name), cmd.params))
                sf()
                sf("%s %s (%s) {", cmd.returnType, membName, paramStr)
                with sf.indentBlock():
                    sf("assert(_%s !is null, \"%s was not loaded.\");", membName, cmd.name)
                    sf("return _%s(%s);", membName, argStr)
                sf("}")

            sf()
            for cmd in self.globalCmds:
                spacer = " " * (maxLen - len(cmd.name))
                # vkCmdName => CmdName
                membName = cmd.name[2:]
                sf("private PFN_%s%s _%s;", cmd.name, spacer, membName)
        sf("}")

    def issueInstanceCmds(self, sf):
        maxLen = 0
        for f in self.features:
            for cmd in f.instanceCmds:
                maxLen = max(maxLen, len(cmd.name))

        sf()
        sf("// Instance commands")
        sf()
        sf("final class VkInstanceCmds {")
        with sf.indentBlock():
            feats = [f for f in self.features if len(f.instanceCmds) > 0]
            sf()
            sf("this (VkInstance instance, VkGlobalCmds globalCmds) {")
            with sf.indentBlock():
                sf("auto loader = globalCmds._GetInstanceProcAddr;")
                for i, f in enumerate(feats):
                    if i != 0:
                        sf()
                    sf("// %s", f.name)
                    f.beginGuard(sf)
                    for cmd in f.instanceCmds:
                        spacer = " " * (maxLen - len(cmd.name))
                        membName = cmd.name[2:]
                        sf(
                            "_%s%s = cast(PFN_%s)%sloader(instance, \"%s\");",
                            membName, spacer, cmd.name, spacer, cmd.name
                        )
                    f.endGuard(sf)
            sf("}")

            for f in feats:
                sf()
                f.beginGuard(sf)
                for i, cmd in enumerate(f.instanceCmds):
                    spacer = " " * (maxLen - len(cmd.name))
                    membName = cmd.name[2:]     # vkCmdName => CmdName
                    paramStr = ", ".join(map((lambda p: "{} {}".format(p.typeStr, p.name)), cmd.params))
                    argStr = ", ".join(map((lambda p: p.name), cmd.params))
                    if i == 0:  sf("/// Commands for %s", f.name)
                    else:       sf("/// ditto")
                    sf("%s %s (%s) {", cmd.returnType, membName, paramStr)
                    with sf.indentBlock():
                        sf("assert(_%s !is null, \"%s was not loaded. Required by %s\");", membName, cmd.name, f.name)
                        sf("return _%s(%s);", membName, argStr)
                    sf("}")
                f.endGuard(sf)

            for f in feats:
                sf()
                sf("// fields for %s", f.name)
                f.beginGuard(sf)
                for cmd in f.instanceCmds:
                    spacer = " " * (maxLen - len(cmd.name))
                    # vkCmdName => CmdName
                    membName = cmd.name[2:]
                    sf("private PFN_%s%s _%s;", cmd.name, spacer, membName)
                f.endGuard(sf)
        sf("}")

    def issueDeviceCmds(self, sf):
        maxLen = 0
        for f in self.features:
            for cmd in f.deviceCmds:
                maxLen = max(maxLen, len(cmd.name))

        sf()
        sf("// Device commands")
        sf()
        sf("final class VkDeviceCmds {")
        with sf.indentBlock():
            feats = [f for f in self.features if len(f.deviceCmds) > 0]
            sf()
            sf("this (VkDevice device, VkInstanceCmds instanceCmds) {")
            with sf.indentBlock():
                sf("auto loader = instanceCmds._GetDeviceProcAddr;")
                for i, f in enumerate(feats):
                    if i != 0:
                        sf()
                    sf("// %s", f.name)
                    f.beginGuard(sf)
                    for cmd in f.deviceCmds:
                        spacer = " " * (maxLen - len(cmd.name))
                        membName = cmd.name[2:]
                        sf(
                            "_%s%s = cast(PFN_%s)%sloader(device, \"%s\");",
                            membName, spacer, cmd.name, spacer, cmd.name
                        )
                    f.endGuard(sf)
            sf("}")

            for f in feats:
                sf()
                f.beginGuard(sf)
                for i, cmd in enumerate(f.deviceCmds):
                    spacer = " " * (maxLen - len(cmd.name))
                    membName = cmd.name[2:]     # vkCmdName => CmdName
                    paramStr = ", ".join(map((lambda p: "{} {}".format(p.typeStr, p.name)), cmd.params))
                    argStr = ", ".join(map((lambda p: p.name), cmd.params))
                    if i == 0:  sf("/// Commands for %s", f.name)
                    else:       sf("/// ditto")
                    sf("%s %s (%s) {", cmd.returnType, membName, paramStr)
                    with sf.indentBlock():
                        sf("assert(_%s !is null, \"%s was not loaded. Requested by %s\");", membName, cmd.name, f.name)
                        sf("return _%s(%s);", membName, argStr)
                    sf("}")
                f.endGuard(sf)

            for f in feats:
                sf()
                sf("// fields for %s", f.name)
                f.beginGuard(sf)
                for cmd in f.deviceCmds:
                    spacer = " " * (maxLen - len(cmd.name))
                    # vkCmdName => CmdName
                    membName = cmd.name[2:]
                    sf("private PFN_%s%s _%s;", cmd.name, spacer, membName)
                f.endGuard(sf)
        sf("}")
