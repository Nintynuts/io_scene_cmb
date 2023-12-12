import os, array, bpy, bmesh, io

from .cmb import *
from .utils import *
from .ctrTexture import DecodeBuffer
from .materials import generateMaterial

# TODO: Clean up

def loadCmbFiles(operator):
    root = get_or_add_root()

    dirname = os.path.dirname(operator.filepath)
    for file in operator.files:
        path = os.path.join(dirname, file.name)
        with open(path, "rb") as f:
            loadCmbSafe(f, os.path.split(path)[0], file.name, bpy.context.collection, root)

    return {"FINISHED"}

def loadCmbSafe(f: io.BufferedReader, folderName: str, fileName: str, collection, parent):
    try:
        loadCmb(f, folderName, collection, parent)        
    except Exception as ex:
        print(f"Failed to load CMB {fileName}")
        print(ex)

def loadCmb(f: io.BufferedReader, folderName, collection, parent):
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
            bmv = bm.verts.new(readVector(f, cmb, i, vb.position, shape.position, 3, 3))
            if (bindices[i][1] != SkinningMode.Smooth):
                bmv.co = transformPosition(bmv.co, boneTransforms[bindices[i][0]])

            # Normal
            if hasNrm:
                v.nrm = readVector(f, cmb, i, vb.normal, shape.normal, 3, 3)

                if (bindices[i][1] != SkinningMode.Smooth):
                    v.nrm = transformNormal(v.nrm, boneTransforms[bindices[i][0]])

            # Color
            if hasClr:
                elements = 3 if bpy.app.version < (2, 80, 0) else 4
                v.clr = readVector(f, cmb, i, vb.color, shape.color, 4, elements)

            # UV0
            if hasUv0:
                v.uv0 = readVector(f, cmb, i, vb.uv0, shape.uv0, 2, 2)

            # UV1
            if hasUv1:
                v.uv1 = readVector(f, cmb, i, vb.uv1, shape.uv1, 2, 2)

            # UV2
            if hasUv2:
                v.uv2 = readVector(f, cmb, i, vb.uv2, shape.uv2, 2, 2)

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

        if hasUv0 or hasUv1 or hasUv2:

            for uv_layer in obj.data.uv_layers:
                # Set the active UV map
                obj.data.uv_layers.active = uv_layer

                # Get linked UV islands
                islands = find_uv_islands(nmesh)

                wraps = False

                # Iterate over UV islands
                for i, island in enumerate(islands):
                    min_u, max_u = math.inf, -math.inf
                    min_v, max_v = math.inf, -math.inf

                    # Iterate over UV coordinates in the island
                    for loop_index in island:
                        uv_coords = uv_layer.data[loop_index].uv
                        min_u = min(min_u, uv_coords[0])
                        max_u = max(max_u, uv_coords[0])
                        min_v = min(min_v, uv_coords[1])
                        max_v = max(max_v, uv_coords[1])

                    delta_u = max_u - min_u
                    delta_v = max_v - min_v

                    wraps_u = delta_u > 1 or math.ceil(min_u) == math.floor(max_u) and min_u % 1 != 0 and max_u % 1 != 0
                    wraps_v = delta_v > 1 or math.ceil(min_v) == math.floor(max_v) and min_v % 1 != 0 and max_v % 1 != 0
                    
                    if (not (wraps_u or wraps_v)):
                        continue
                
                    if not wraps:
                        texture = cmb.materials[mesh.materialIndex].TextureMappers[1]
                        print(f"Model: {cmb.name}, Mesh: {obj.name}, Texure: {os.path.basename(textureNames[texture.textureID])}, WrapS: {texture.wrapS.name}, WrapT: {texture.wrapT.name}")
                        wraps = True

                    text = f"Island: {i}, Vertices: {len(island)}"

                    # Check if UVs in the island cross the repeat boundary
                    if wraps_u:
                        text += f", U: {min_u:6.3f} <-> {max_u:6.3f} ({delta_u:.3f})"

                    if wraps_v:
                        text += f", V: {min_v:6.3f} <-> {max_v:6.3f} ({delta_v:.3f})"

                    print(text)

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

    skl_obj.parent = parent
    return skl_obj

def readVector(f: BufferedReader, cmb: Cmb, i, vb: AttributeSlice, shape: VertexAttribute, size: int, sizeBlender: int):
    f.seek(cmb.vatrOfs + vb.startOfs + shape.start + size * getDataTypeSize(shape.dataType) * i)
    return [e * shape.scale for e in readArray(f, sizeBlender, shape.dataType)]

def find_uv_islands(mesh):
    loop_to_uv = mesh.uv_layers.active.data

    # Create a lookup of loop index to polygons
    uv_to_polygons = {}
    for i, poly in enumerate(mesh.polygons):
        for loop_index in poly.loop_indices:
            uv_coord = tuple(loop_to_uv[loop_index].uv)
            if uv_coord not in uv_to_polygons:
                uv_to_polygons[uv_coord] = set()
            uv_to_polygons[uv_coord].add(i)

    # Create a lookup of each polygon's status (0: not used, 1: used)
    polygon_status = {i: 0 for i in range(len(mesh.polygons))}

    # Create a list of islands
    islands = []

    def traverse_island(start_polygon_index, island_set):
        stack = [start_polygon_index]
        
        while stack:
            polygon_index = stack.pop()

            # Add loop uv indices to the island set
            island_set.update(mesh.polygons[polygon_index].loop_indices)

            poly_uvs = set(tuple(loop_to_uv[loop_index].uv) for loop_index in mesh.polygons[polygon_index].loop_indices)
            # Iterate over the polygon loop indices
            for loop_index in mesh.polygons[polygon_index].loop_indices:
                # Get linked polygons using the lookup
                linked_polygons = uv_to_polygons.get(tuple(loop_to_uv[loop_index].uv), set())

                # Iterate over linked polygons
                for linked_polygon_index in linked_polygons:
                    linked_poly_uvs = set(tuple(loop_to_uv[linked_loop_index].uv) for linked_loop_index in mesh.polygons[linked_polygon_index].loop_indices)
                    # If the polygon hasn't been used and has two shared loop indices with the previous polygon
                    if (polygon_index != linked_polygon_index
                        and polygon_status[linked_polygon_index] == 0
                        and len(poly_uvs.intersection(linked_poly_uvs)) >= 2):
                        # Mark the polygon as used
                        polygon_status[linked_polygon_index] = 1
                        stack.append(linked_polygon_index)

    # Iterate over polygons
    for polygon_index in range(len(mesh.polygons)):
        # If the polygon isn't used
        if polygon_status[polygon_index] == 0:
            # Create a set of loop uv indices containing the first polygon indices
            current_island = set()

            # Mark the polygon as used
            polygon_status[polygon_index] = 1

            # Start traversing the island
            traverse_island(polygon_index, current_island)

            # Add the island set to the list of islands
            islands.append(current_island)

    return islands

class Vertex(object):
    def __init__(self):
        self.pos = []
        self.nrm = []
        self.clr = []
        self.uv0 = []
        self.uv1 = []
        self.uv2 = []