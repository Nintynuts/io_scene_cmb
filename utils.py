import struct, math, mathutils, bpy

from io import BufferedReader
from mathutils import Vector
from .cmbEnums import DataTypes

def get_or_add_root():
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    space.shading.type = 'MATERIAL'

    bpy.context.scene.render.engine = 'CYCLES'  # Idc if you don't like cycles

    # Find an existing object by name
    rootName = "Root"
    root = bpy.data.objects.get(rootName)

    # If the object doesn't exist, create a new one
    if root is None:
        root = bpy.data.objects.new(rootName, None)
        bpy.context.collection.objects.link(root)
        bpy.context.view_layer.objects.active = root
        root.scale = (0.01, 0.01, 0.01)
        root.rotation_euler = Vector([math.radians(90),0,0])

    return root


def getFlag(value, index, increment):
    index += increment
    return ((value >> index) & 1) != 0

def align(file: BufferedReader, size=4):
    while (file.tell() % size):
        file.seek(file.tell() + 1)

def readUByte(file: BufferedReader) -> int:
    return struct.unpack("B", file.read(1))[0]

def readByte(file: BufferedReader) -> int:
    return struct.unpack("b", file.read(1))[0]

def readBytes(file: BufferedReader, count) -> list[int]:
    return [readUByte(file) for _ in range(count)]

def readUShort(file: BufferedReader) -> int:
    return struct.unpack("<H", file.read(2))[0]

def readShort(file: BufferedReader) -> int:
    return struct.unpack("<h", file.read(2))[0]

def readUInt32(file: BufferedReader) -> int:
    return struct.unpack("<I", file.read(4))[0]

def readInt32(file: BufferedReader) -> int:
    return struct.unpack("<i", file.read(4))[0]

def readFloat(file: BufferedReader) -> float:
    return struct.unpack("<f", file.read(4))[0]

def readArray(file: BufferedReader, elements, datatype: DataTypes = DataTypes.Float) -> list:
    return [readDataType(file, datatype) for _ in range(elements)]

def readDataType(file: BufferedReader, dt: DataTypes):
    match dt:
        case DataTypes.Byte:
            return readByte(file)
        case DataTypes.UByte:
            return readUByte(file)
        case DataTypes.Short:
            return readShort(file)
        case DataTypes.UShort:
            return readUShort(file)
        case DataTypes.Int:
            return readInt32(file)
        case DataTypes.UInt:
            return readUInt32(file)
        case _:
            return readFloat(file)

def getDataTypeSize(dt) -> int:
    match dt:
        case DataTypes.Byte | DataTypes.UByte:
            return 1
        case DataTypes.Short | DataTypes.UShort:
            return 2
        case _:
            return 4

def readString(file: BufferedReader, length=0) -> str:
    if (length > 0):
        return file.read(length).decode("ASCII").replace("\x00", '')
    else:
        return ''.join(iter(lambda: file.read(1).decode("ASCII"), '\x00' or ''))

def readOffsetString(file: BufferedReader, offset: int, length: int = 0) -> str:
    temp = file.tell()
    file.seek(offset)
    value = readString(file, length)
    file.seek(temp)
    return value

# Ported from OpenTK
# blender might have something but I'm too lazy to check
def dot(left, right) -> float:
    return left[0] * right.x + left[1] * right.y + left[2] * right.z

def transformPosition(pos, mat) -> list[float]:
    p = [0.0, 0.0, 0.0]
    p[0] = dot(pos, mat.col[0].xyz) + mat.row[3].x
    p[1] = dot(pos, mat.col[1].xyz) + mat.row[3].y
    p[2] = dot(pos, mat.col[2].xyz) + mat.row[3].z
    return p

def transformNormalInverse(norm, invMat) -> list[float]:
    n = [0.0, 0.0, 0.0]
    n[0] = dot(norm, invMat[0].xyz)
    n[1] = dot(norm, invMat[1].xyz)
    n[2] = dot(norm, invMat[2].xyz)
    return n

def transformNormal(norm, mat):
    invMat = mat.inverted()
    return transformNormalInverse(norm, invMat)

def fromEulerAngles(rotation):
    x_rotation = mathutils.Quaternion((1, 0, 0), rotation[0])
    y_rotation = mathutils.Quaternion((0, 1, 0), rotation[1])
    z_rotation = mathutils.Quaternion((0, 0, 1), rotation[2])
    q = z_rotation @ y_rotation @ x_rotation

    if q.w < 0:
        q.negate()
    return q

def getWorldTransform(bone):
    # get translation, rotation, and scale from bone
    T = mathutils.Matrix.Translation(bone.translation)
    R = mathutils.Euler(bone.rotation, 'XYZ').to_matrix().to_4x4()
    # construct transformation matrix
    return R @ T

def fromAxisAngle(axis, angle):
    return mathutils.Quaternion((
        math.cos(angle / 2),
        axis[0] * math.sin(angle / 2),
        axis[1] * math.sin(angle / 2),
        axis[2] * math.sin(angle / 2),
    ))

def fromEulerAngles(rot):
    x = fromAxisAngle((1, 0, 0), rot[0])
    y = fromAxisAngle((0, 1, 0), rot[1])
    z = fromAxisAngle((0, 0, 1), rot[2])
    q = z * y * x
    if q.w < 0:
        q *= -1
    return q
