#! /usr/bin/env python3

if __name__ == "__main__":

    import sys
    import os
    from os import path
    import argparse

    import xml.etree.ElementTree as etree

    rootDir = path.dirname(path.realpath(__file__))
    regDir = path.join(rootDir, 'registry')
    sys.path.insert(0, regDir)

    from reg import Registry
    from vkdgen import *

    parser = argparse.ArgumentParser(description='Vulkan D bindings generator')
    parser.add_argument('--package', dest='package', default='vkd',
                        help='D package of generated modules [vkd]')
    parser.add_argument('--dest', dest='dest', default=path.join(rootDir, 'd'),
                        help='Destination folder for generated files [(vkdgen)/d]')
    args = parser.parse_args()

    pack = args.package
    srcDir = path.join(args.dest, pack.replace('.', os.sep))

    os.makedirs(srcDir, exist_ok=True)

    files = []

    # first we generate files from the hand-written templates
    templateFiles = [ 'loader.d.in' ]
    for tf in templateFiles:
        from string import Template
        with open(path.join(rootDir, 'templates', tf), mode="r") as ifile:
            t = Template(ifile.read())
            ofname = path.join(srcDir, tf.replace('.in', ''))
            with open(ofname, mode="w") as ofile:
                ofile.write(t.substitute(pack=pack))
            files.append(ofname)


    # Turn a list of strings into a regexp string matching exactly those strings
    # Turn a list of strings into a regexp string matching exactly those strings
    def makeREstring(list, default = None):
        if len(list) > 0 or default == None:
            return '^(' + '|'.join(list) + ')$'
        else:
            return default

    # Descriptive names for various regexp patterns used to select
    # versions and extensions

    defaultExtensions = 'vulkan'
    extensions = []
    removeExtensions = []
    emitExtensions = []
    features = []
    allFeatures     = allExtensions = '.*'
    noFeatures      = noExtensions = None
    addExtensionsPat     = makeREstring(extensions)
    removeExtensionsPat  = makeREstring(removeExtensions)
    emitExtensionsPat    = makeREstring(emitExtensions, allExtensions)
    featuresPat          = makeREstring(features, allFeatures)
    allVersions       = allExtensions = ".*"
    noVersions        = noExtensions = None

    platformExts = [
        "VK_KHR_display",
        "VK_KHR_swapchain",
        "VK_KHR_win32_surface",
        "VK_KHR_xcb_surface",
        "VK_KHR_wayland_surface",
        "VK_KHR_surface",
        "VK_EXT_debug_report",
    ]

    addPlatformExtensionsRE = makeREstring(platformExts)
    emitPlatformExtensionsRE = makeREstring(platformExts)

    buildList = [
        DGeneratorOptions(
            filename = path.join(srcDir, "vk.d"),
            module = "{}.vk".format(pack),
            apiname = "vulkan",
            regFile = path.join(regDir, "vk.xml"),
            versions = featuresPat,
            addExtensions = addPlatformExtensionsRE,
            removeExtensions = None,
            emitExtensions = emitPlatformExtensionsRE,
        ),
    ]

    for opts in buildList:
        gen = DGenerator()
        reg = Registry()
        reg.loadElementTree( etree.parse( opts.regFile ))
        reg.setGenerator( gen )
        reg.apiGen(opts)
        files.append(opts.filename)

    import platform
    libname=''
    if platform.system() == 'Windows':
        libname='vkd.lib'
    else:
        libname='libvkd.a'

    with open(path.join(rootDir, 'dmd_args.txt'), "w") as argfile:
        argfile.write('-lib\n')
        argfile.write('-I'+args.dest+'\n')
        argfile.write('-of'+path.join(rootDir, libname)+'\n')
        for f in files:
            argfile.write(f + '\n')
