import io, os, bpy

from io import BufferedReader
from .utils import *
from .cmbEnums import GLTextureFormat
from .ctrTexture import DecodeBuffer

class CTXB:

    def __init__(self, f: BufferedReader):
        self.Magic = readString(f, 4)
        self.FileSize = readUInt32(f)
        self.ChunkCount = readUInt32(f)
        f.seek(f.tell()+4); # padding
        self.ChunkOffset = readUInt32(f)
        self.TextureDataOffset = readUInt32(f)

        self.Chunks = [Chunk(f) for _ in range(self.ChunkCount)]

        for chunk in self.Chunks:
            for texture in chunk.Textures:
                f.seek(self.TextureDataOffset + texture.DataOffset)
                texture.Data = f.read(texture.ImageSize)

class Chunk:

    def __init__(self, f: BufferedReader):
        self.Magic = readString(f, 4)
        self.SectionSize = readUInt32(f)
        self.TextureCount = readUInt32(f)

        self.Textures = [Texture(f) for _ in range(self.TextureCount)]

class Texture:

    Data: list = []

    def __init__(self, f: BufferedReader):        
        self.ImageSize = readUInt32(f)
        self.MaxLevel = readUShort(f)
        readUShort(f) # unknown
        self.Width = readUShort(f)
        self.Height = readUShort(f)
        self.TextureFormat = GLTextureFormat(readUInt32(f))
        self.DataOffset = readUInt32(f)
        self.Name = readString(f, 16)
        
def loadCtxb(file: BufferedReader, folderName: str, fileName: str):
    try:
        ctxb = CTXB(file)

        for chunk in ctxb.Chunks:
            for t in chunk.Textures:
                name = t.Name if t.Name != "" else os.path.splitext(fileName)[0]
                format = t.TextureFormat
                imagePath = os.path.join(folderName, f"{name}.png")
                if os.path.exists(imagePath):
                    continue
                
                image = bpy.data.images.new(t.Name, t.Width, t.Height, alpha=True)
                image.pixels = DecodeBuffer(t.Data, t.Width, t.Height, format, format is GLTextureFormat.ETC1a4 or format is GLTextureFormat.ETC1)
                image.update()  # Updates the display image                
                image.filepath_raw = imagePath
                image.file_format = 'PNG'
                image.save()

    except Exception as ex:
        print("Failed to load CTXB file")
        print(ex)

def loadCtxbFiles(operator):
    root = get_or_add_root()

    dirname = os.path.dirname(operator.filepath)
    for file in operator.files:
        path = os.path.join(dirname, file.name)
        with open(path, "rb") as f:
            loadCtxb(f, os.path.dirname(path), file.name)

    return {"FINISHED"}