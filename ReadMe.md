# vkdgen

Vulkan D bindings generator

This is not a Dub package and is not intended to become one. Users can copy
the files they need from the `d` folder, or generate their own with
`gen_d_files.py`:
```
$ ./gen_d_files.py -h
usage: gen_d_files.py [-h] [--package PACKAGE] [--dest DEST]

Vulkan D bindings generator

optional arguments:
  -h, --help         show this help message and exit
  --package PACKAGE  D package of generated modules [vkd]
  --dest DEST        Destination folder for generated files [(vkdgen)/d]
```

The generated bindings do not include any global symbol such as `vkCreateBuffer`.
Instead there are the following definitions:
```d
final class VkGlobalCmds {

    this (PFN_vkGetInstanceProcAddr loader) {
        // load all global commands
    }

    VkResult CreateInstance (...) { ... }

}

final class VkInstanceCmds {
    this (VkInstance instance, VkGlobalCmds globalCmds) {
        // load all instance commands
    }

    VkResult CreateDevice (VkInstance inst, ...) { ... }
}

final class VkDeviceCmds {
    this (VkDevice device, VkInstanceCmds instanceCmds) {
        // load all device commands
    }

    VkResult CreateBuffer (VkDevice device, ...) { ... }
}
```
Client usage could be as follow
```d
import vkd.vk;
import vkd.loader : loadVulkanGlobalCmds();

// load global commands
auto globVk = loadVulkanGlobalCmds();

// load instance commands
VkInstance inst;
VkInstanceCreateInfo instCreateInfo = // ...
globVk.CreateInstance(&instCreateInfo, null, &inst);
auto instVk = new VkInstanceCmds(inst, globVk);

// load device commands
VkPhysicalDevice phDev = // ...
VkDevice dev;
VkDeviceCreateInfo devCreateInfo = // ...
instVk.CreateDevice(phDev, &devCreateInfo, null, &dev);
auto vk = new VkDeviceCmds(dev, instVk);

// vk.CreateBuffer(dev, ...);
```
