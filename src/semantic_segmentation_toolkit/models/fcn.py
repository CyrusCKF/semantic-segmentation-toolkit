from torch import nn
from torch.hub import load_state_dict_from_url
from torchvision import models as TM
from torchvision.models.segmentation.fcn import (
    FCN,
    FCNHead,
    fcn_resnet50,
    fcn_resnet101,
)

from ..datasets import VOC_LABELS
from .backbones import *
from .model_registry import SegWeights, SegWeightsEnum, register_model
from .model_utils import _validate_weights_input

register_model()(fcn_resnet50)
register_model()(fcn_resnet101)


class FCN_ResNet34_Weights(SegWeightsEnum):
    VOC2012 = SegWeights(
        "fcn/fcn_resnet34-voc2012-500x500-20250221.pth",
        VOC_LABELS,
        "Trained on PASCAL VOC 2012 dataset",
    )
    DEFAULT = VOC2012


@register_model(weights_enum=FCN_ResNet34_Weights)
def fcn_resnet34(
    num_classes: int | None = None,
    weights: FCN_ResNet34_Weights | str | None = None,
    progress: bool = True,
    aux_loss: bool = False,
    weights_backbone: TM.ResNet34_Weights | str | None = TM.ResNet34_Weights.DEFAULT,
) -> nn.Module:
    weights_model = FCN_ResNet34_Weights.resolve(weights)
    weights_model, weights_backbone, num_classes = _validate_weights_input(
        weights_model, weights_backbone, num_classes
    )

    backbone_model = TM.resnet34(weights=weights_backbone, progress=progress)
    backbone = ResNetBackbone(backbone_model)
    replace_layer_name(backbone, {-1: "out", -2: "aux"})

    channels = backbone.layer_channels()
    classifier = FCNHead(channels["out"], num_classes)
    aux_classifier = FCNHead(channels["aux"], num_classes) if aux_loss else None
    model = FCN(backbone, classifier, aux_classifier)

    if weights_model is not None:
        state_dict = load_state_dict_from_url(weights_model.url, progress=progress)
        model.load_state_dict(state_dict)
    return model


@register_model()
def fcn_mobilenet_v3_large(
    num_classes: int | None = None,
    weights: str | None = None,
    progress: bool = True,
    aux_loss: bool = False,
    weights_backbone: (
        TM.MobileNet_V3_Large_Weights | str | None
    ) = TM.MobileNet_V3_Large_Weights.DEFAULT,
) -> nn.Module:
    if weights is not None:
        raise NotImplementedError("Weights is not supported yet")
    _, weights_backbone, num_classes = _validate_weights_input(
        None, weights_backbone, num_classes
    )

    backbone_model = TM.mobilenet_v3_large(weights=weights_backbone, progress=progress)
    backbone = MobileNetV3Backbone(backbone_model)
    replace_layer_name(backbone, {-1: "out", -4: "aux"})

    channels = backbone.layer_channels()
    classifier = FCNHead(channels["out"], num_classes)
    aux_classifier = FCNHead(channels["aux"], num_classes) if aux_loss else None
    return FCN(backbone, classifier, aux_classifier)


@register_model()
def fcn_vgg16(
    num_classes: int | None = None,
    weights: str | None = None,
    progress: bool = True,
    aux_loss: bool = False,
    weights_backbone: TM.VGG16_Weights | str | None = TM.VGG16_Weights.DEFAULT,
) -> nn.Module:
    if weights is not None:
        raise NotImplementedError("Weights is not supported yet")
    _, weights_backbone, num_classes = _validate_weights_input(
        None, weights_backbone, num_classes
    )

    backbone_model = TM.vgg16(weights=weights_backbone, progress=progress)
    backbone = VGGBackbone(backbone_model)
    replace_layer_name(backbone, {-1: "out", -2: "aux"})

    channels = backbone.layer_channels()
    classifier = FCNHead(channels["out"], num_classes)
    aux_classifier = FCNHead(channels["aux"], num_classes) if aux_loss else None
    return FCN(backbone, classifier, aux_classifier)
