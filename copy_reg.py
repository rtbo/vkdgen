#! /usr/bin/env python3

import os
from os import path

root_dir = path.dirname(path.realpath(__file__))
local_reg_dir = path.join(root_dir, 'registry')
os.makedirs(local_reg_dir, exist_ok=True)

def copy_reg(reg_dir, files):
    import shutil
    for f in files:
        file_path = path.join(reg_dir, f)
        if not path.isfile(file_path):
            raise RuntimeError(file_path + ' could not be found')
        shutil.copy2(file_path, path.join(local_reg_dir, path.basename(f)))

vk_files = [ 'registry/vk.xml', 'registry/reg.py', 'registry/generator.py' ]
copy_reg(path.join(root_dir, 'Vulkan-Headers'), vk_files)
