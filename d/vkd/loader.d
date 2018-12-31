
/// Loader module for vkdgen.
/// Loading bindings is done in 3 steps as follow:
/// ---
/// import vkd.loader;
///
/// // load global commands
/// auto globVk = loadVulkanGlobalCmds();
///
/// // load instance commands
/// VkInstance inst;
/// VkInstanceCreateInfo instCreateInfo = // ...
/// globVk.CreateInstance(&instCreateInfo, null, &inst);
/// auto instVk = new VkInstanceCmds(inst, globVk);
///
/// // load device commands
/// VkPhysicalDevice phDev = // ...
/// VkDevice dev;
/// VkDeviceCreateInfo devCreateInfo = // ...
/// instVk.CreateDevice(phDev, &devCreateInfo, null, &dev);
/// auto vk = new VkDeviceCmds(dev, instVk);
///
/// // vk.CreateBuffer(dev, ...);
/// ---
module vkd.loader;

import vkd.vk : VkGlobalCmds;

import std.exception;

/// A handle to a shared library
alias SharedLib = void*;
/// A handle to a shared library symbol
alias SharedSym = void*;

/// Opens a shared library.
/// Return null in case of failure.
SharedLib openSharedLib(string name);

/// Load a symbol from a shared library.
/// Return null in case of failure.
SharedSym loadSharedSym(SharedLib lib, string name);

/// Close a shared library
void closeSharedLib(SharedLib lib);


/// Generic Dynamic lib symbol loader.
/// Symbols loaded with such loader must be cast to the appropriate function type.
alias SymbolLoader = SharedSym delegate (in string name);


version(Posix)
{
    import std.string : toStringz;
    import core.sys.posix.dlfcn;

    SharedLib openSharedLib(string name)
    {
        return dlopen(toStringz(name), RTLD_LAZY);
    }

    SharedSym loadSharedSym(SharedLib lib, string name)
    {
        return dlsym(lib, toStringz(name));
    }

    void closeSharedLib(SharedLib lib)
    {
        dlclose(lib);
    }
}
version(Windows)
{
    import std.string : toStringz;
    import core.sys.windows.winbase;

    SharedLib openSharedLib(string name)
    {
        return LoadLibraryA(toStringz(name));
    }

    SharedSym loadSharedSym(SharedLib lib, string name)
    {
        return GetProcAddress(lib, toStringz(name));
    }

    void closeSharedLib(SharedLib lib)
    {
        FreeLibrary(lib);
    }
}


@nogc nothrow pure
{
    /// Make a Vulkan version identifier
    uint VK_MAKE_VERSION( uint major, uint minor, uint patch ) {
        return ( major << 22 ) | ( minor << 12 ) | ( patch );
    }

    /// Make Vulkan-1.0 identifier
    uint VK_API_VERSION_1_0() { return VK_MAKE_VERSION( 1, 0, 0 ); }
    /// Make Vulkan-1.1 identifier
    uint VK_API_VERSION_1_1() { return VK_MAKE_VERSION( 1, 1, 0 ); }

    /// Extract major version from a Vulkan version identifier
    uint VK_VERSION_MAJOR( uint ver ) { return ver >> 22; }
    /// Extract minor version from a Vulkan version identifier
    uint VK_VERSION_MINOR( uint ver ) { return ( ver >> 12 ) & 0x3ff; }
    /// Extract patch version from a Vulkan version identifier
    uint VK_VERSION_PATCH( uint ver ) { return ver & 0xfff; }
}

/// Vulkan null handle
enum VK_NULL_HANDLE = null;
version(X86_64) {
    /// Vulkan non-dispatchable null handle
    enum VK_NULL_ND_HANDLE = null;
}
else {
    /// Vulkan non-dispatchable null handle
    enum VK_NULL_ND_HANDLE = 0;
}

/// Load global commands from Vulkan DLL/Shared object.
/// Returns: a VkGlobalCmds object
VkGlobalCmds loadVulkanGlobalCmds() {
    version( Windows )
        enum libName = "vulkan-1.dll";
    else version( Posix )
        enum libName = "libvulkan.so.1";
    else
        static assert (false, "Vulkan bindings not supported on this OS");

    auto lib = enforce(openSharedLib(libName), "Cannot open "~libName);

    auto getInstanceProcAddr = enforce(
        cast(PFN_vkGetInstanceProcAddr)loadSharedSym(lib, "vkGetInstanceProcAddr"),
        "Could not load vkGetInstanceProcAddr from "~libName
    );

    return new VkGlobalCmds(getInstanceProcAddr);
}
