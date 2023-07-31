
from io import BufferedReader
from .utils import *
from .cmbEnums import GLTextureFormat

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