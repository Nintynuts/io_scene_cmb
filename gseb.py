import os, math

from enum import IntEnum
from .utils import *
from .gar import loadGar
from .import_cmb import loadCmb

class DataType(IntEnum):    
    UInt = 0, 
    String = 1, 
    Float = 2 

class SceneField(object):
    def __init__(self, f):
        self.id1 = readUByte(f)
        self.id2 = readUByte(f)
        self.id3 = readUByte(f)
        f.seek(f.tell()+5)
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
            match (field.id1, field.id2, field.id3):
                case (198, 117, 97) | (59, 121, 121):
                    self.modelName = readString(f, size)
                    self.fromMdlFolder = True
                case (205, 200, 155):
                    self.modelName = readString(f, size)
                case (45, 149, 201):
                    self.roomNo = readUInt32(f)
                case (129, 110, 114):
                    self.verticalOffset = readFloat(f)
                case (170 | 171 | 172, 92, 84):
                    self.boundsDimensions[field.id1-170] = readUInt32(f)
                case (217 | 218 | 219, 239, 123):
                    self.position[field.id1-217] = readFloat(f)
                case (100 | 101 | 102, 5, 122):
                    self.rotation[field.id1-100] = readFloat(f)
                case _:
                    f.seek(f.tell() + size)

def loadGseb(f, folderName, root):
    numItems = readUInt32(f)
    numFields = readUInt32(f)
    itemsOff = readUInt32(f)
    itemSize = readUInt32(f)
    fields = [SceneField(f) for _ in range(numFields)]
    scene = [SceneObj(f, fields, itemSize) for _ in range(numItems)]
    mapNo = int(os.path.basename(folderName)[3:])
    romFSpath = os.path.dirname(os.path.dirname(folderName))

    for obj in scene:
        if hasattr(obj, "roomNo"):
            roomCollection = bpy.data.collections.get(f"Room {obj.roomNo}")
            if not roomCollection:
                roomCollection = bpy.data.collections.new(f"Room {obj.roomNo}")
                bpy.context.scene.collection.children.link(roomCollection)
        else:
            roomCollection = bpy.context.scene.collection

        if obj.position == [0,0,0] and obj.rotation == [0,0,0]:
            continue
        
        bounds = bpy.data.objects.new(f"{obj.modelName}.bounds", None)
        roomCollection.objects.link(bounds)
        origin = bounds
        parent = root
        model = None
        
        if obj.modelName != "(null)":
            if (obj.fromMdlFolder):
                path = os.path.join(romFSpath, "model", obj.modelName)
            else:
                path = os.path.join(romFSpath, "mapmdl", f"map{mapNo}", f"room_{str(obj.roomNo).zfill(2)}", obj.modelName)

            if os.path.exists(f"{path}.cmb"):
                with open(f"{path}.cmb", "rb") as reader:
                    model = loadCmb(reader, path, roomCollection, parent)
            elif os.path.exists(f"{path}.zar"):
                with open(f"{path}.zar", "rb") as reader:
                    model = loadGar(reader, path, roomCollection, parent)
            elif os.path.exists(f"{path}.gar"):
                with open(f"{path}.gar", "rb") as reader:
                    model = loadGar(reader, path, roomCollection, parent)
            else:
                print(f"Warning: File '{path}' does not exist.")

        if model != None:
            model.parent = root
            parent = model
            origin = model
            
        bounds.parent = parent

        rotation = mathutils.Euler([math.radians(d) for d in obj.rotation], 'XYZ').to_matrix().to_4x4()
        translation = mathutils.Matrix.Translation(Vector(obj.position))
        origin.matrix_local = translation @ rotation

        bounds.empty_display_type = 'CUBE'
        bounds.empty_display_size = 0.5
        #bounds.matrix_local = bounds.matrix_local @ mathutils.Matrix.Translation(Vector([0,obj.boundsDimensions[1]/2,0]))            
        if obj.boundsDimensions != [0,0,0]:
            bounds.scale = Vector(obj.boundsDimensions)

def loadGsebFiles(operator):
    root = get_or_add_root()

    dirname = os.path.dirname(operator.filepath)
    for file in operator.files:
        path = os.path.join(dirname, file.name)
        with open(path, "rb") as f:
            loadGseb(f, os.path.dirname(path), root)

    return {"FINISHED"}
