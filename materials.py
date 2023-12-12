import bpy

from mathutils import Vector
from typing import Tuple
from bpy.types import ShaderNode, ShaderNodeInvert, ShaderNodeSeparateRGB, ShaderNodeRGB, NodeSocket
from .cmb import *

def getNodeFromSocket(socket: NodeSocket, type) -> ShaderNode:
    for link in socket.links:
        if isinstance(link.to_node, type):
            return link.to_node
    return None

def getInvertNode(nodes, links, source: NodeSocket) -> ShaderNode:
    invert = getNodeFromSocket(source, ShaderNodeInvert)
    if invert is not None:
        return invert

    invert = nodes.new("ShaderNodeInvert")
    links.new(source, invert.inputs['Color'])
    return invert

def getSeparateRGBNode(nodes, links, source: NodeSocket) -> ShaderNode:
    separate = getNodeFromSocket(source, ShaderNodeSeparateRGB)
    if separate is not None:
        return separate

    separate = nodes.new("ShaderNodeSeparateRGB")
    links.new(source, separate.inputs['Image'])
    return separate

def getSourceNode(m: Material, stage: Combiner, textures: list, constantColourNodes: list,
                  previous: Tuple[NodeSocket, NodeSocket], previousBuffer: Tuple[NodeSocket, NodeSocket], diffuse: Tuple[NodeSocket, NodeSocket], vertexColour: Tuple[NodeSocket, NodeSocket],
                  nodes: list, sourceType: TexCombinerSource) -> Tuple[NodeSocket, NodeSocket]:
    match sourceType:
        case TexCombinerSource.Texture0:
            return (textures[0].outputs['Color'], textures[0].outputs['Alpha'])
        case TexCombinerSource.Texture1:
            return (textures[1].outputs['Color'], textures[1].outputs['Alpha'])
        case TexCombinerSource.Texture2:
            return (textures[2].outputs['Color'], textures[2].outputs['Alpha'])
        case TexCombinerSource.Texture3:
            return (textures[3].outputs['Color'], textures[3].outputs['Alpha'])
        case TexCombinerSource.PrimaryColor:
            return vertexColour
        case TexCombinerSource.Constant:
            colour = constantColourNodes[stage.constColorIndex]
            return (colour[0].outputs['Color'], colour[1].outputs['Value'])
        case TexCombinerSource.Previous:
            return previous
        case TexCombinerSource.PreviousBuffer:
            return previousBuffer
        case TexCombinerSource.FragmentPrimaryColor:
            return diffuse
        case TexCombinerSource.FragmentSecondaryColor:
            colour = nodes.new("ShaderNodeRGB")
            colour.label = "Fragment Secondary Colour"
            colour.outputs['Color'].default_value = (0.0, 0.0, 0.0, 1.0)
            alpha = nodes.new("ShaderNodeValue")
            alpha.label = "Fragment Secondary Alpha"
            alpha.outputs['Value'].default_value = 1.0
            return (colour.outputs['Color'], alpha.outputs['Value'])

def getCombinerOpOutput(nodes: list, links: list, source: Tuple[ShaderNode, ShaderNode], colourOp: TexCombinerColorOp) -> NodeSocket:
    match colourOp:
        case TexCombinerColorOp.Color:
            return source[0]
        case TexCombinerColorOp.Alpha:
            return source[1]
        case TexCombinerColorOp.Red:
            channel = getSeparateRGBNode(nodes, links, source[0])
            return channel.outputs['R']
        case TexCombinerColorOp.Green:
            channel = getSeparateRGBNode(nodes, links, source[0])
            return channel.outputs['G']
        case TexCombinerColorOp.Blue:
            channel = getSeparateRGBNode(nodes, links, source[0])
            return channel.outputs['B']
        case TexCombinerColorOp.OneMinusColor:
            invert = getInvertNode(nodes, links, source[0])
            return invert.outputs['Color']
        case TexCombinerColorOp.OneMinusAlpha:
            invert = getInvertNode(nodes, links, source[1])
            return invert.outputs['Color']
        case TexCombinerColorOp.OneMinusRed:
            invert = getInvertNode(nodes, links, source[0])
            channel = getSeparateRGBNode(nodes, links, invert.outputs["Color"])
            return channel.outputs['R']
        case TexCombinerColorOp.OneMinusGreen:
            invert = getInvertNode(nodes, links, source[0])
            channel = getSeparateRGBNode(nodes, links, invert.outputs["Color"])
            return channel.outputs['G']
        case TexCombinerColorOp.OneMinusBlue:
            invert = getInvertNode(nodes, links, source[0])
            channel = getSeparateRGBNode(nodes, links, invert.outputs["Color"])
            return channel.outputs['B']

def getCombinerNodes(m: Material, stageIdx: int, stage: Combiner, textures: list, constantColourNodes: list, nodes: list, links: list,
                     previous: Tuple[ShaderNode, ShaderNode], previousBuffer: Tuple[ShaderNode, ShaderNode], diffuse: Tuple[ShaderNode, ShaderNode], vertexColour: Tuple[ShaderNode, ShaderNode],
                     mathNodeName, combinerMode: TexCombineMode,
                     source0: TexCombinerSource, source1: TexCombinerSource, source2: TexCombinerSource,
                     operand0: TexCombinerColorOp, operand1: TexCombinerColorOp, operand2: TexCombinerColorOp) -> NodeSocket:
    src0 = getSourceNode(m, stage, textures, constantColourNodes,
                         previous, previousBuffer, diffuse, vertexColour, nodes, source0)
    src0output = getCombinerOpOutput(nodes, links, src0, operand0)

    if combinerMode == TexCombineMode.Replace:
        return src0output

    else:
        src1 = getSourceNode(m, stage, textures, constantColourNodes,
                             previous, previousBuffer, diffuse, vertexColour, nodes, source1)
        src1output = getCombinerOpOutput(nodes, links, src1, operand1)

        if combinerMode == TexCombineMode.Interpolate \
           or combinerMode == TexCombineMode.MultAdd \
           or combinerMode == TexCombineMode.AddMult:

            src2 = getSourceNode(m, stage, textures, constantColourNodes,
                                 previous, previousBuffer, diffuse, vertexColour, nodes, source2)
            src2output = getCombinerOpOutput(nodes, links, src2, operand2)

            if combinerMode == TexCombineMode.Interpolate:
                interp = nodes.new("ShaderNodeMixRGB")
                links.new(src0output, interp.inputs['Color2'])
                links.new(src1output, interp.inputs['Color1'])
                links.new(src2output, interp.inputs['Fac'])
                interp.label = f"Stage {stageIdx}"
                return interp.outputs['Color']

            elif combinerMode == TexCombineMode.MultAdd:
                multiply = nodes.new(mathNodeName)
                multiply.operation = 'MULTIPLY'
                links.new(src0output, multiply.inputs[0])
                links.new(src1output, multiply.inputs[1])

                add = nodes.new(mathNodeName)
                add.operation = 'ADD'
                links.new(multiply.outputs[0], add.inputs[0])
                links.new(src2output, add.inputs[1])
                add.label = f"Stage {stageIdx}"
                return add.outputs[0]

            elif combinerMode == TexCombineMode.AddMult:
                add = nodes.new(mathNodeName)
                add.operation = 'ADD'
                links.new(src0output, add.inputs[0])
                links.new(src1output, add.inputs[1])

                multiply = nodes.new(mathNodeName)
                multiply.operation = 'MULTIPLY'
                links.new(add.outputs[0], multiply.inputs[0])
                links.new(src2output, multiply.inputs[1])
                multiply.label = f"Stage {stageIdx}"
                return multiply.outputs[0]

        elif combinerMode == TexCombineMode.Modulate:
            modulate = nodes.new(mathNodeName)
            modulate.operation = 'MULTIPLY'
            links.new(src0output, modulate.inputs[0])
            links.new(src1output, modulate.inputs[1])
            modulate.label = f"Stage {stageIdx}"
            return modulate.outputs[0]

        elif combinerMode == TexCombineMode.Add:
            add = nodes.new(mathNodeName)
            add.operation = 'ADD'
            links.new(src0output, add.inputs[0])
            links.new(src1output, add.inputs[1])
            add.label = f"Stage {stageIdx}"
            return add.outputs[0]

        elif combinerMode == TexCombineMode.AddSigned:
            add = nodes.new(mathNodeName)
            add.operation = 'ADD'
            links.new(src0output, add.inputs[0])
            links.new(src1output, add.inputs[1])
            add.label = f"Stage {stageIdx}"
            return add.outputs[0]

        elif combinerMode == TexCombineMode.Subtract:
            subtract = nodes.new(mathNodeName)
            subtract.operation = 'SUBTRACT'
            links.new(src0output, subtract.inputs[0])
            links.new(src1output, subtract.inputs[1])
            subtract.label = f"Stage {stageIdx}"
            return subtract.outputs[0]

        elif combinerMode == TexCombineMode.DotProduct3Rgb:
            dp = nodes.new("ShaderNodeVectorMath")
            dp.operation = 'DOT_PRODUCT'
            links.new(src0output, dp.inputs[0])
            links.new(src1output, dp.inputs[1])
            dp.label = f"Stage {stageIdx}"
            return dp.outputs[0]

        elif combinerMode == TexCombineMode.DotProduct3Rgba:
            dp = nodes.new("ShaderNodeVectorMath")
            dp.operation = 'DOT_PRODUCT'
            links.new(src0output, dp.inputs[0])
            links.new(src1output, dp.inputs[1])

            # Alpha?

            dp.label = f"Stage {stageIdx}"
            return dp.outputs[0]

def generateMaterial(m: Material, name: str, materialNames: list, textureNames: list):
    mat = bpy.data.materials.new('{}_mat'.format(name))  # Create new material
    mat.use_nodes = True  # Use nodes
    mat.use_backface_culling = True
    mat.specular_intensity = 0.0
    materialNames.append(mat.name)

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    # Get existing shader node to use
    sdr = nodes.get("Principled BSDF")
    out = nodes.get("Material Output")  # Output node
    links.new(sdr.outputs['BSDF'], out.inputs['Surface'])

    if m.alphaTestEnabled:
        mat.blend_method = 'BLEND'

    textures = []
    for i in range(m.TextureMappersUsed):
        tm = m.TextureMappers[i]
        tc = m.TextureCoords[i]

        # Create new texture node
        texture = nodes.new("ShaderNodeTexImage")

        # Set the texture's image
        image = bpy.data.images.get(textureNames[tm.textureID])
        if image is None:
            image = bpy.data.images.load(textureNames[tm.textureID])
        texture.image = image
        textures.append(texture)

        #print("material: {}, texture: {}".format(matIdx, textureNames[tm.textureID]))

        texCoord = nodes.new("ShaderNodeUVMap")
        texCoord.uv_map = f"UV{tc.uvChannel}"

        if tm.wrapS == TextureWrapMode.Mirror or tm.wrapT == TextureWrapMode.Mirror:
            separate = nodes.new('ShaderNodeSeparateXYZ')
            combine = nodes.new('ShaderNodeCombineXYZ')
            links.new(texCoord.outputs['UV'], separate.inputs['Vector'])
            links.new(combine.outputs['Vector'], texture.inputs['Vector'])

            if tm.wrapS == TextureWrapMode.Mirror:
                pingpong = nodes.new('ShaderNodeMath')
                pingpong.operation = 'PINGPONG'
                pingpong.inputs[1].default_value = 1.0  # Scale
                links.new(separate.outputs['X'], pingpong.inputs['Value'])
                links.new(pingpong.outputs['Value'], combine.inputs['X'])
            else:
                links.new(separate.outputs['X'], combine.inputs['X'])

            if tm.wrapT == TextureWrapMode.Mirror:
                pingpong = nodes.new('ShaderNodeMath')
                pingpong.operation = 'PINGPONG'
                pingpong.inputs[1].default_value = 1.0  # Scale
                links.new(separate.outputs['Y'], pingpong.inputs['Value'])
                links.new(pingpong.outputs['Value'], combine.inputs['Y'])
            else:
                links.new(separate.outputs['Y'], combine.inputs['Y'])
        else:
            links.new(texCoord.outputs['UV'], texture.inputs['Vector'])

    constantColourNodes = [None] * len(m.constantColors)

    for c in range(len(m.constantColors)):
        colour = nodes.new("ShaderNodeRGB")
        colour.label = "Constant {} Colour".format(c)
        colour.outputs['Color'].default_value = Vector([n/255.0 for n in m.constantColors[c]])
        alpha = nodes.new("ShaderNodeValue")
        alpha.label = "Constant {} Alpha".format(c)
        alpha.outputs['Value'].default_value = m.constantColors[c][-1]/255.0
        constantColourNodes[c] = (colour, alpha)

    # These are actual colours, so they work
    sdr.inputs['Subsurface Color'].default_value = Vector([b/255.0 for b in m.ambientColor])
    sdr.inputs['Emission'].default_value = Vector([b/255.0 for b in m.emissionColor])

    # BSDF doesn't support tinted specular because it's determined by the light source.
    # So instead we just use the Green channel as that contributes most to intensity.
    sdr.inputs['Roughness'].default_value = m.specular0Color[1]/255.0
    sdr.inputs['Specular'].default_value = m.specular1Color[1]/255.0

    vertexColourNode = nodes.new("ShaderNodeVertexColor")
    vertexColourNode.label = "Fragment Primary Colour"
    vertexColour = (vertexColourNode.outputs['Color'], vertexColourNode.outputs['Alpha'])

    colour = nodes.new("ShaderNodeRGB")
    colour.label = "Diffuse Colour"
    colour.outputs['Color'].default_value = Vector([b/255.0 for b in m.diffuseColor])
    alpha = nodes.new("ShaderNodeValue")
    alpha.label = "Diffuse Alpha"
    alpha.outputs['Value'].default_value = m.diffuseColor[-1] / 255.0
    diffuseNodes = (colour, alpha)
    diffuse = (colour.outputs['Color'], alpha.outputs['Value'])

    colour = nodes.new("ShaderNodeRGB")
    colour.label = "Buffer Colour"
    colour.outputs['Color'].default_value = Vector([b/255.0 for b in m.bufferColor])
    alpha = nodes.new("ShaderNodeValue")
    alpha.label = "Buffer Alpha"
    alpha.outputs['Value'].default_value = m.bufferColor[-1] / 255.0
    bufferNodes = (colour, alpha)
    buffer = (colour.outputs['Color'], alpha.outputs['Value'])
    previous = bufferNodes
    previousBuffer = bufferNodes

    for stageIdx in range(m.texEnvStageCount):
        stage = m.texEnvStages[stageIdx]

        colour = getCombinerNodes(m, stageIdx, stage, textures, constantColourNodes, nodes, links,
                                    previous, previousBuffer, diffuse, vertexColour,
                                    "ShaderNodeVectorMath", stage.combinerModeColor,
                                    stage.sourceColor0, stage.sourceColor1, stage.sourceColor2,
                                    stage.operandColor0, stage.operandColor1, stage.operandColor2)

        if colour is None:
            raise ValueError("Colour cannot be none")

        if stage.scaleColor != 1:
            scale = nodes.new("ShaderNodeVectorMath")
            scale.operation = 'MULTIPLY'
            links.new(colour, scale.inputs[0])
            scale.inputs[1].default_value = (stage.scaleColor, stage.scaleColor, stage.scaleColor)
            colour = scale.outputs[0]

        alpha = getCombinerNodes(m, stageIdx, stage, textures, constantColourNodes, nodes, links,
                                    previous, previousBuffer, diffuse, vertexColour,
                                    "ShaderNodeMath", stage.combinerModeAlpha,
                                    stage.sourceAlpha0, stage.sourceAlpha1, stage.sourceAlpha2,
                                    stage.operandAlpha0, stage.operandAlpha1, stage.operandAlpha2)

        if stage.scaleAlpha != 1:
            scale = nodes.new("ShaderNodeMath")
            scale.operation = 'MULTIPLY'
            links.new(alpha, scale.inputs[0])
            scale.inputs[1].default_value = stage.scaleAlpha
            alpha = scale.outputs[0]

        previousBuffer = previous
        previous = (colour, alpha)

    links.new(previous[0], sdr.inputs['Base Color'])
    links.new(previous[1], sdr.inputs['Alpha'])

    for (colour, alpha) in constantColourNodes:
        if len(colour.outputs[0].links) == 0:
            nodes.remove(colour)
        if len(alpha.outputs[0].links) == 0:
            nodes.remove(alpha)

    if len(vertexColour[0].links) == 0 and len(vertexColour[1].links) == 0:
        nodes.remove(vertexColourNode)

    if len(diffuse[0].links) == 0:
        nodes.remove(diffuseNodes[0])
    if len(diffuse[1].links) == 0:
        nodes.remove(diffuseNodes[1])

    if len(buffer[0].links) == 0:
        nodes.remove(bufferNodes[0])
    if len(buffer[1].links) == 0:
        nodes.remove(bufferNodes[1])