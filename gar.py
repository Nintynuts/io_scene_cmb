import io

from io import BufferedReader
from .utils import *

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
        self.FileSize = readUInt32(f)
        self.FileOffset = readUInt32(f)
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
        self.FileSize = readUInt32(f)
        self.Name = None if isZarFormat else readOffsetString(f,readUInt32(f))
        self.FileName = readOffsetString(f,readUInt32(f))

class FileEntry:
    def __init__(self, open_file_format_on_load, file_name, file_data):
        self.OpenFileFormatOnLoad = open_file_format_on_load
        self.FileName = file_name
        self.FileData = file_data

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
            self.Files.append(FileEntry(info.Ext == "csab",
                                    f"{info.Name}.{info.Ext}",
                                    self.getSection(f, info.FileOffset, info.FileSize)))

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
            self.Files.append(FileEntry(self.FileInfos[i].FileName.contains("csab"),
                self.FileInfos[i].FileName,
                self.getSection(f, Offsets[i], self.FileInfos[i].FileSize)))
    
    def getSection(self, f: BufferedReader, offset, size):
        f.seek(offset, io.SEEK_SET)
        return f.read(size)
