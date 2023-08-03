import io, os

from io import BufferedReader
from .utils import *
from .ctxb import CTXB
from .ctrTexture import DecodeBuffer
from .cmbEnums import GLTextureFormat

class SystemFileGroup:

    Ids: list[int] = []

    def __init__(self, f: BufferedReader):
        self.FileCount = readUInt32(f)
        self.Unknown = readUInt32(f)
        self.InfoOffset = readUInt32(f)
        self.Name = readOffsetString(f,readUInt32(f))
        self.OffsetToUnknown = readUInt32(f)
        f.seek(f.tell()+12) # padding

class SystemFileInfo:
    def __init__(self, f: BufferedReader, ext):
        self.Ext = ext
        self.DataSize = readUInt32(f)
        self.DataOffset = readUInt32(f)
        self.Name = readOffsetString(f,readUInt32(f))
        f.seek(f.tell()+4)  # padding

class FileGroup:
    def __init__(self, f):
        self.FileCount = readUInt32(f)
        self.DataOffset = readUInt32(f)
        self.InfoOffset = readUInt32(f)
        f.seek(f.tell()+4)  # padding
        self.Ids = []

class FileInfo:
    def __init__(self, f: BufferedReader, isZarFormat: bool):
        self.DataSize = readUInt32(f)
        self.Name = None if isZarFormat else readOffsetString(f,readUInt32(f))
        tokens = os.path.splitext(readOffsetString(f,readUInt32(f)))
        self.FileName = tokens[0]
        self.Ext = tokens[1]

class FileEntry:
    def __init__(self, name, ext, data):
        self.FileName = name
        self.Ext = ext
        self.Data = data

class GAR:
    class VersionMagic:
        ZAR1 = 0  # OOT3D
        GAR2 = 1  # MM3D
        GAR5 = 2  # LM3DS

    Files: list[FileEntry]
    FileGroups: list[SystemFileGroup]
    FileInfos: list[FileInfo]

    def __init__(self, f: BufferedReader):
        self.Files = []
        self.FileGroups = []
        self.FileInfos = []
        
        self.Signature = readString(f, 4)
        if self.Signature == "ZAR\x01":
            self.Version = self.VersionMagic.ZAR1
        elif self.Signature == "GAR\x02":
            self.Version = self.VersionMagic.GAR2
        elif self.Signature == "GAR\x05":
            self.Version = self.VersionMagic.GAR5

        self.FileSize = readUInt32(f)
        self.FileGroupCount = readUShort(f)
        self.FileCount = readUShort(f)
        self.FileGroupOffset = readUInt32(f)
        self.FileInfoOffset = readUInt32(f)
        self.DataOffset = readUInt32(f)
        self.Codename = readString(f, 0x08)

        match self.Codename:
            case "queen" | "jenkins":
                self.readZeldaArchive(f)
            case "agora" | "SYSTEM":
                self.readSystemGrezzoArchive(f)
            case _:
                raise Exception(f"Unexpected codename! {self.Codename}")

    def readSystemGrezzoArchive(self, f: BufferedReader):
        f.seek(self.FileGroupOffset)
        for i in range(self.FileGroupCount):
            self.FileGroups.append(SystemFileGroup(f))

        f.seek(self.FileInfoOffset)
        for i in range(self.FileGroupCount):
            for _ in range(self.FileGroups[i].FileCount):
                self.FileInfos.append(SystemFileInfo(f, self.FileGroups[i].Name))

        f.seek(self.DataOffset)
        for i in range(self.FileCount):
            info = self.FileInfos[i]
            self.Files.append(FileEntry(info.Name, info.Ext, self.getSection(f, info.DataOffset, info.DataSize)))

    def readZeldaArchive(self, f: BufferedReader):
        f.seek(self.FileGroupOffset)
        for i in range(self.FileGroupCount):
            self.FileGroups.append(FileGroup(f))

        for i in range(self.FileGroupCount):
            self.FileGroups[i].Ids = readArray(f, self.FileGroups[i].FileCount, DataTypes.UInt)

        f.seek(self.FileInfoOffset)
        for i in range(self.FileGroupCount):
            for f in range(self.FileGroups[i].FileCount):
                self.FileInfos.append(FileInfo(f, self.Version == self.VersionMagic.ZAR1))

        f.seek(self.DataOffset)
        Offsets = readArray(f, self.FileCount, DataTypes.UInt)
        for i in range(len(self.FileInfos)):
            self.Files.append(FileEntry(self.FileInfos[i].FileName, self.getSection(f, Offsets[i], self.FileInfos[i].DataSize)))
    
    def getSection(self, f: BufferedReader, offset, size):
        f.seek(offset, io.SEEK_SET)
        return f.read(size)

def loadGar(garReader: BufferedReader, folderName, collection, parent):
    gar = GAR(garReader)

    # iterate the texture files first so we can access them when loading the model
    for file in gar.Files:
        if file.Ext == "ctxb":
            ctxb = CTXB(io.BufferedReader(io.BytesIO(file.Data)))
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

    firstModel = None
    group = None
    
    for file in gar.Files:
        if file.Ext == "cmb":
            from .import_cmb import loadCmb
            model = loadCmb(io.BufferedReader(io.BytesIO(file.Data)), folderName, collection, parent)
            if firstModel == None:
                firstModel = model
            else:
                if group == None:
                    group = bpy.data.objects.new(folderName.replace(os.path.dirname(folderName),"").strip(os.path.sep), None)
                    collection.objects.link(group)
                    group.parent = parent
                    firstModel.parent = group
                model.parent = group

        if file.Ext == "gar":
            folderName = os.path.join(folderName, file.FileName)
            if not os.path.exists(folderName):
                os.mkdir(folderName)
            loadGar(io.BufferedReader(io.BytesIO(file.Data)), folderName, collection, parent)

    return firstModel if group == None else group
    
def loadGarFiles(operator):
    root = get_or_add_root()
    
    dirname = os.path.dirname(operator.filepath)
    for file in operator.files:
        path = os.path.join(dirname, file.name)
        
        folderName = os.path.splitext(path)[0]
        if not os.path.exists(folderName):
            os.mkdir(folderName)
        with open(path, "rb") as reader:
            loadGar(reader, folderName, bpy.context.scene.collection, root)

    return {"FINISHED"}