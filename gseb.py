import os, io, math

from enum import IntEnum
from .utils import *
from .gar import GAR
from .ctxb import CTXB
from .ctrTexture import DecodeBuffer
from .import_cmb import LoadModel
from .cmbEnums import GLTextureFormat

class DataType(IntEnum):    
    UInt = 0, 
    String = 1, 
    Float = 2 

class SceneField(object):
    def __init__(self, f):
        self.id = readUByte(f)
        f.seek(f.tell()+7)
        self.offset = readUShort(f)
        f.seek(f.tell()+1)
        self.type = DataType(readUByte(f))

class SceneObj(object):
    def __init__(self, f, fields: list[SceneField], endOffset):
        
        self.boundsDimensions = [0, 0, 0]
        self.position = [0, 0, 0]
        self.rotation = [0, 0, 0]

        field_iterator = zip(fields, [field.offset for field in fields[1:]] + [endOffset])

        for field, next_offset in field_iterator:
            size = next_offset - field.offset
            match field.id:
                case 198:
                    self.modelName = readString(f, size)
                    self.fromMdlFolder = True
                case 205:
                    self.modelName = readString(f, size)
                case 45:
                    self.roomNo = readUInt32(f)
                case 129:
                    self.verticalOffset = readFloat(f)
                case 170 | 171 | 172:
                    self.boundsDimensions[field.id-170] = readUInt32(f)
                case 217 | 218 | 219:
                    self.position[field.id-217] = readFloat(f)
                case 100 | 101 | 102:
                    self.rotation[field.id-100] = readFloat(f)
                case _:
                    f.seek(f.tell() + size)


def load_gseb(operator, context):
    root = get_or_add_root()

    with open(operator.filepath, "rb") as f:
        numItems = readUInt32(f)
        numFields = readUInt32(f)
        itemsOff = readUInt32(f)
        itemSize = readUInt32(f)
        fields = [SceneField(f) for _ in range(numFields)]
        scene = [SceneObj(f, fields, itemsOff) for _ in range(numItems)]
        dirname = os.path.dirname(operator.filepath)
        mapNo = int(os.path.basename(dirname)[3:])
        romFSpath = os.path.dirname(os.path.dirname(dirname))

        roomCollections = {}
        for obj in scene:
            roomCollection = roomCollections.get(obj.roomNo)
            if not roomCollection:
                roomCollection = bpy.data.collections.new(f"Room {obj.roomNo}")
                bpy.context.scene.collection.children.link(roomCollection)
                roomCollections[obj.roomNo] = roomCollection

            bounds = bpy.data.objects.new(f"{obj.modelName}.bounds", None)
            roomCollection.objects.link(bounds)
            origin = bounds
            parent = root

            if obj.modelName != "(null)":
                if (obj.fromMdlFolder):
                    path = os.path.join(romFSpath, "model", obj.modelName)
                else:
                    path = os.path.join(romFSpath, "mapmdl", f"map{mapNo}", f"room_{str(obj.roomNo).zfill(2)}", obj.modelName)

                reader = None

                if os.path.exists(f"{path}.cmb"):
                    reader = open(f"{path}.cmb", "rb")
                elif os.path.exists(f"{path}.zar"):
                    reader = readArchive(f"{path}.zar", path)
                elif os.path.exists(f"{path}.gar"):
                    reader = readArchive(f"{path}.gar", path)
                else:
                    print(f"Warning: File '{path}' does not exist.")

                if reader is None:
                    continue

                model = LoadModel(reader, path, roomCollection)
                model.parent = parent
                parent = model
                origin = model
                reader.close()
            
            rotation = mathutils.Euler([math.radians(d) for d in obj.rotation], 'XYZ').to_matrix().to_4x4()
            translation = mathutils.Matrix.Translation(Vector(obj.position))
            origin.matrix_local = translation @ rotation
            
            bounds.empty_display_type = 'CUBE'
            bounds.empty_display_size = 0.5
            bounds.matrix_local = bounds.matrix_local @ mathutils.Matrix.Translation(Vector([0,obj.boundsDimensions[1]/2,0]))
            bounds.scale = Vector(obj.boundsDimensions)
            bounds.parent = parent
                    
            # Force Blender UI to update
            # bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)

            # Pause the script execution for a short duration
            # time.sleep(0.01)

    return {"FINISHED"}

def readArchive(path, folderName):
    with open(path, "rb") as garReader:
        gar = GAR(garReader)

        # iterate the texture files firse so we can access them when loading the model
        for file in gar.Files:
            if str.endswith(file.FileName, ".ctxb"):
                ctxbReader = io.BufferedReader(io.BytesIO(file.FileData))
                ctxb = CTXB(ctxbReader)
                if not os.path.exists(folderName):
                    os.mkdir(folderName)

                for chunk in ctxb.Chunks:
                    for t in chunk.Textures:
                        imagePath = os.path.join(folderName, f"{t.Name}.png")
                        if os.path.exists(imagePath):
                            continue
                        
                        image = bpy.data.images.new(t.Name, t.Width, t.Height, alpha=True)
                        image.pixels = DecodeBuffer(t.Data, t.Width, t.Height, t.TextureFormat, t.TextureFormat is GLTextureFormat.ETC1a4 or GLTextureFormat.ETC1)
                        image.update()  # Updates the display image                
                        image.filepath_raw = imagePath
                        image.file_format = 'PNG'
                        image.save()
        
        # only load the first model
        for file in gar.Files:
            if str.endswith(file.FileName, ".cmb"):
                return io.BufferedReader(io.BytesIO(gar.Files[0].FileData))
            
        print(f"Warning: Archive'{path}' does not contain same name cmb.")
        return None
