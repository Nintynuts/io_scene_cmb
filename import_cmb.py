import os, array, bpy, bmesh, io

from .cmb import *
from .utils import *
from .ctrTexture import DecodeBuffer
from .materials import generateMaterial

# TODO: Clean up

def load_cmb(operator, context):
    root = get_or_add_root()

    dirname = os.path.dirname(operator.filepath)
    for file in operator.files:
        path = os.path.join(dirname, file.name)
        with open(path, "rb") as f:
            model = LoadModel(f, os.path.split(path)[0], bpy.context.collection)
            model.parent = root

    return {"FINISHED"}

def LoadModel(f: io.BufferedReader, folderName, collection):
    cmb = readCmb(f)
    vb = cmb.vatr  # VertexBufferInfo
    boneTransforms = {}

    # ################################################################
    # Build skeleton
    # ################################################################

    skeleton = bpy.data.armatures.new(f"{cmb.name}_armature")  # Create new armature
    # Create new armature object
    skl_obj = bpy.data.objects.new(cmb.name, skeleton)
    skl_obj.show_in_front = True
    collection.objects.link(skl_obj)  # Link armature to the scene
    bpy.context.view_layer.objects.active = skl_obj  # Select the skeleton for editing
    bpy.ops.object.mode_set(mode='EDIT')  # Set to edit mode

    for bone in cmb.skeleton:
        # Save the matrices so we don't have to recalculate them for single-binded meshes later
        matrix = boneTransforms[bone.id] = getWorldTransform(bone)
        eb = skeleton.edit_bones.new(f'bone_{bone.id}')
        eb.matrix = matrix.transposed()
        eb.use_connect = True

        # Inherit rotation/scale and use deform
        # eb.use_inherit_scale = eb.use_inherit_rotation = eb.use_deform = True

        # Assign parent bone
        if bone.parentId != -1:
            eb.parent = skeleton.edit_bones[bone.parentId]
            eb.tail = (boneTransforms[bone.parentId] @ Vector(bone.translation)).to_3d()
            boneTransforms[bone.id] = boneTransforms[bone.parentId] @ boneTransforms[bone.id]

        eb.tail[1] += 0.001  # Blender will delete all zero-length bones

        #print(f"bone: {bone.id}, parent: {bone.parentId}, position: {bone.translation}, rotation: {bone.rotation}, scale: {bone.scale}")

    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')

    # ################################################################
    # Add Textures
    # ################################################################
    textureNames = []  # Used as a lookup

    if (not os.path.exists(folderName)):
        os.mkdir(folderName)

    for t in cmb.textures:
        f.seek(cmb.texDataOfs + t.dataOffset)
        fileName = os.path.join(folderName, t.name) + ".png"
        textureNames.append(fileName)

        # Note: Pixels are in floating-point values
        if (cmb.texDataOfs != 0):
            image = bpy.data.images.new(t.name, t.width, t.height, alpha=True)
            pixels = DecodeBuffer(readArray(f, t.dataLength, DataTypes.UByte),
                                    t.width, t.height, t.imageFormat, t.isETC1)
            image.pixels = pixels
            image.update()  # Updates the display image                
            image.filepath_raw = fileName
            image.file_format = 'PNG'
            image.save()
            # Pack the image into the .blend file. True = pack as .png
            # packed_data = struct.pack('f' * len(pixels), *pixels)
            # image.pack(data=packed_data, data_len=len(packed_data))

    # ################################################################
    # Add Materials
    # ################################################################
    materialNames = []  # Used as a lookup

    for matIdx in range(len(cmb.materials)):
        generateMaterial(cmb.materials[matIdx], cmb.name, materialNames, textureNames)

    # ################################################################
    # Build Meshes
    # ################################################################

    for m in range(len(cmb.meshes)):
        mesh = cmb.meshes[m]
        shape = cmb.shapes[mesh.shapeIndex]
        indices = [faces for pset in shape.primitiveSets for faces in pset.primitive.indices]
        vertexCount = max(indices)+1
        vertices = []
        bindices = {}

        #print(f"mesh: {m}, shape: {mesh.shapeIndex}, bone: {mesh.ID}, material: {mesh.materialIndex}")

        # Python doesn't have increment operator (afaik) so this must be ugly...
        inc = 0  # increment
        hasNrm = getFlag(shape.vertFlags, 1, inc)
        if cmb.version > 6:
            inc += 1  # Skip "HasTangents" for now
        hasClr = getFlag(shape.vertFlags, 2, inc)
        hasUv0 = getFlag(shape.vertFlags, 3, inc)
        hasUv1 = getFlag(shape.vertFlags, 4, inc)
        hasUv2 = getFlag(shape.vertFlags, 5, inc)
        hasBi = getFlag(shape.vertFlags, 6, inc)
        hasBw = getFlag(shape.vertFlags, 7, inc)

        # Create new mesh
        # ID is used for visibility animations
        nmesh = bpy.data.meshes.new('shape_{}'.format(mesh.shapeIndex))
        nmesh.use_auto_smooth = True  # Needed for custom split normals
        nmesh.materials.append(bpy.data.materials.get(materialNames[mesh.materialIndex]))  # Add material to mesh

        obj = bpy.data.objects.new('mesh_{}'.format(m), nmesh)  # Create new mesh object
        obj.parent = skl_obj  # Set parent skeleton
        collection.objects.link(obj)
        # obj.parent_type = 'BONE'
        # obj.parent_bone = 'bone_{}'.format(mesh.ID)

        ArmMod = obj.modifiers.new(skl_obj.name, "ARMATURE")
        ArmMod.object = skl_obj  # Set the modifiers armature

        for bone in bpy.data.armatures[skeleton.name].bones.values():
            obj.vertex_groups.new(name=bone.name)

        # Get bone indices. We need to get these first because-
        # each primitive has it's own bone table
        for s in shape.primitiveSets:
            for i in s.primitive.indices:
                if (hasBi and s.skinningMode != SkinningMode.Single):
                    f.seek(cmb.vatrOfs + vb.bIndices.startOfs +
                            shape.bIndices.start + i * shape.boneDimensions)
                    for bi in range(shape.boneDimensions):
                        index = int(readDataType(f, shape.bIndices.dataType) * shape.bIndices.scale)
                        bindices[i * shape.boneDimensions + bi] = (s.boneTable[index], s.skinningMode)
                else:
                    # For single-bind meshes
                    bindices[i] = (s.boneTable[0], s.skinningMode)

        if shape.primSetCount == 1 and shape.primitiveSets[0].skinningMode != SkinningMode.Smooth and shape.primitiveSets[0].boneTableCount == 1:
            obj.matrix_world = boneTransforms[shape.primitiveSets[0].boneTable[0]]

        # Create new bmesh
        bm = bmesh.new()
        bm.from_mesh(nmesh)
        weight_layer = bm.verts.layers.deform.new()  # Add new deform layer

        # TODO: Support constants
        # Get vertices
        for i in range(vertexCount):
            v = Vertex()  # Ugly because I don't care :)

            # Position
            bmv = bm.verts.new(ReadVector(f, cmb, i, vb.position, shape.position, 3, 3))
            if (bindices[i][1] != SkinningMode.Smooth):
                bmv.co = transformPosition(bmv.co, boneTransforms[bindices[i][0]])

            # Normal
            if hasNrm:
                v.nrm = ReadVector(f, cmb, i, vb.normal, shape.normal, 3, 3)

                if (bindices[i][1] != SkinningMode.Smooth):
                    v.nrm = transformNormal(v.nrm, boneTransforms[bindices[i][0]])

            # Color
            if hasClr:
                elements = 3 if bpy.app.version < (2, 80, 0) else 4
                v.clr = ReadVector(f, cmb, i, vb.color, shape.color, 4, elements)

            # UV0
            if hasUv0:
                v.uv0 = ReadVector(f, cmb, i, vb.uv0, shape.uv0, 2, 2)

            # UV1
            if hasUv1:
                v.uv1 = ReadVector(f, cmb, i, vb.uv1, shape.uv1, 2, 2)

            # UV2
            if hasUv2:
                v.uv2 = ReadVector(f, cmb, i, vb.uv2, shape.uv2, 2, 2)

            # Bone Weights
            if hasBw:
                # For smooth meshes
                f.seek(cmb.vatrOfs + vb.bWeights.startOfs + shape.bWeights.start + i * shape.boneDimensions)
                for j in range(shape.boneDimensions):
                    weight = round(readDataType(f, shape.bWeights.dataType) * shape.bWeights.scale, 2)
                    if (weight > 0):
                        bmv[weight_layer][bindices[i * shape.boneDimensions + j][0]] = weight
            else:
                # For single-bind meshes
                bmv[weight_layer][bindices[i][0]] = 1.0

            vertices.append(v)

        # Must always be called after adding/removing vertices or accessing them by index
        bm.verts.ensure_lookup_table()
        bm.verts.index_update()  # Assign an index value to each vertex

        for i in range(0, len(indices), 3):
            try:
                face = bm.faces.new(bm.verts[j] for j in indices[i:i + 3])
                face.material_index = mesh.materialIndex
                face.smooth = True
            except:  # face already exists
                continue

        uv_layer0 = bm.loops.layers.uv.new("UV0") if (hasUv0) else None
        uv_layer1 = bm.loops.layers.uv.new("UV1") if (hasUv1) else None
        uv_layer2 = bm.loops.layers.uv.new("UV2") if (hasUv2) else None
        col_layer = bm.loops.layers.color.new("Colour") if (hasClr) else None

        for face in bm.faces:
            for loop in face.loops:
                if hasUv0:
                    uv0 = vertices[loop.vert.index].uv0
                    loop[uv_layer0].uv = (uv0[0], uv0[1])
                if hasUv1:
                    uv1 = vertices[loop.vert.index].uv1
                    loop[uv_layer1].uv = (uv1[0], uv1[1])
                if hasUv2:
                    uv2 = vertices[loop.vert.index].uv2
                    loop[uv_layer2].uv = (uv2[0], uv2[1])
                if hasClr:
                    loop[col_layer] = vertices[loop.vert.index].clr

        # Assign bmesh to newly created mesh
        nmesh.update()
        bm.to_mesh(nmesh)
        bm.free()  # Remove all the mesh data immediately and disable further access

        # Blender has no idea what normals are
        # TODO: Add an option
        UseCustomNormals = True
        if (UseCustomNormals and hasNrm):
            nmesh.normals_split_custom_set_from_vertices([vertices[i].nrm for i in range(len(vertices))])
        else:
            clnors = array.array('f', [0.0] * (len(nmesh.loops) * 3))
            nmesh.loops.foreach_get("normal", clnors)
            nmesh.normals_split_custom_set(tuple(zip(*(iter(clnors),) * 3)))

    return skl_obj

def ReadVector(f, cmb, i, vb, shape, size, sizeBlender):
    f.seek(cmb.vatrOfs + vb.startOfs + shape.start + size * getDataTypeSize(shape.dataType) * i)
    return [e * shape.scale for e in readArray(f, sizeBlender, shape.dataType)]

class Vertex(object):
    def __init__(self):
        self.pos = []
        self.nrm = []
        self.clr = []
        self.uv0 = []
        self.uv1 = []
        self.uv2 = []