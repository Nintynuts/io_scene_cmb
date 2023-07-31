bl_info = {
    "name":         "CMB Import",
    "author":       "M-1 (Discord: M-1#1972)",
    "blender":      (2, 90, 0),
    "version":      (1,0,0),
    "location":     "File > Import",
    "warning":      "This add-on is an early release and bugs may occur",
    "description":  "Import Grezzo's \"Ctr Model Binary\" and \"Grezzo Scene Entity Binary\" file(s)",
    "category":     "Import-Export",
    "wiki_url":     "",
    "tracker_url":  "",
}

import bpy
from bpy.props import *
from bpy_extras.io_utils import ImportHelper

# ################################################################
# Import/Export
# ################################################################
class ImportCmb(bpy.types.Operator, ImportHelper):
    bl_idname = "import.cmb"
    bl_label = "Import CMB"
    
    filename_ext = ".cmb"
    filter_glob: bpy.props.StringProperty(default="*.cmb", options={'HIDDEN'})
    files: bpy.props.CollectionProperty(type=bpy.types.OperatorFileListElement, options={'HIDDEN', 'SKIP_SAVE'})
    directory: bpy.props.StringProperty(subtype='FILE_PATH', options={'HIDDEN', 'SKIP_SAVE'})
        
    def execute( self, context ):
        from .import_cmb import load_cmb
        return load_cmb(self, context)
        
class ImportGseb(bpy.types.Operator, ImportHelper):
    bl_idname = "import.gseb"
    bl_label = "Import GSEB"
    
    filename_ext = ".gseb"
    filter_glob: bpy.props.StringProperty(default="*.gseb", options={'HIDDEN'})
    files: bpy.props.CollectionProperty(type=bpy.types.OperatorFileListElement, options={'HIDDEN', 'SKIP_SAVE'})
    directory: bpy.props.StringProperty(subtype='FILE_PATH', options={'HIDDEN', 'SKIP_SAVE'})
        
    def execute( self, context ):
        from .gseb import load_gseb
        return load_gseb(self, context)

# ################################################################
# Common
# ################################################################

def menu_func_import( self, context ):
    self.layout.operator( ImportCmb.bl_idname, text="CtrModelBinary (.cmb)")
    self.layout.operator( ImportGseb.bl_idname, text="GrezzoSceneBinary (.gseb)")

def register():
    print("Registering CMB\n")
    bpy.utils.register_class(ImportCmb)
    bpy.utils.register_class(ImportGseb)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    
def unregister():
    print("Unregistering CMB\n")
    bpy.utils.unregister_class(ImportCmb)
    bpy.utils.unregister_class(ImportGseb)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    
if __name__ == "__main__":
    register()