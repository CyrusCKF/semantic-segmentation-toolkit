import torch
from torch import Tensor, nn
from torch.hub import load_state_dict_from_url
from torch.nn import functional as F
from torchvision.models.resnet import (
    ResNet18_Weights,
    ResNet50_Weights,
    resnet18,
    resnet50,
)

from ..datasets import CITYSCAPES_LABELS
from .backbones import (
    ResNetBackbone,
    Xception_Weights,
    XceptionBackbone,
    replace_layer_name,
    xception_original,
)
from .model_registry import SegWeights, SegWeightsEnum, register_model
from .model_utils import _validate_weights_input


class BiSeNet(nn.Module):
    """Implement BiSeNet from [BiSeNet: Bilateral Segmentation Network for
    Real-time Semantic Segmentation](https://arxiv.org/abs/1808.00897)"""

    def __init__(
        self,
        num_classes: int,
        backbone: nn.Module,
        backbone_channels: dict[str, int],
        path_channels: int = 128,
        use_aux=False,
    ) -> None:
        """
        Args:
            backbone: Return features which must contain keys "16x" and "32x"
            backbone_channels: Number of channels in "16x" and "32x"
            path_channels: The output channels of spatial path and context path
            aux_16x_weight: If :param:`use_aux` is `True`, multiply the auxillary
                outputs of 16x downsampled in context path by this value
        """
        super().__init__()
        self.backbone = backbone
        self.context_path_stage = ContextPathStage(backbone_channels, path_channels)
        self.spatial_path = SpatialPath(3, path_channels)
        self.ffm = FeatureFusionModule(path_channels * 2, path_channels * 2)

        self.head = BiSeNetHead(path_channels * 2, path_channels * 2, num_classes, 8)
        self.aux_heads = None
        if use_aux:
            self.aux_heads = nn.ModuleDict(
                {
                    "16x": BiSeNetHead(path_channels, path_channels, num_classes, 8),
                    "32x": BiSeNetHead(path_channels, path_channels, num_classes, 16),
                }
            )

    def forward(self, x: Tensor) -> dict[str, Tensor]:
        spatial_out = self.spatial_path(x)
        feature_maps: dict[str, Tensor] = self.backbone(x)
        context_outs: tuple[Tensor, Tensor] = self.context_path_stage(
            feature_maps, spatial_out.shape[2:]
        )
        context_32x, context_16x = context_outs
        combined_out = torch.cat([spatial_out, context_16x], dim=1)
        ffm_out = self.ffm(combined_out)

        main_out = self.head(ffm_out)
        main_out = F.interpolate(main_out, x.shape[2:], mode="bilinear")
        out = {"out": main_out}
        if self.aux_heads is not None:
            aux_out_32x = self.aux_heads["32x"](context_32x)
            aux_out_16x = self.aux_heads["16x"](context_16x)
            aux_out = F.interpolate(
                aux_out_32x, x.shape[2:], mode="bilinear"
            ) + F.interpolate(aux_out_16x, x.shape[2:], mode="bilinear")
            # TODO return a dict of different aux
            out["aux"] = aux_out
        return out


class BiSeNetHead(nn.Sequential):
    def __init__(
        self, in_channels: int, inter_channels: int, out_channels: int, up_factor: int
    ):
        super().__init__(
            ConvNormAct(in_channels, inter_channels, 3),
            Upscale(inter_channels, out_channels, up_factor),
        )


class ContextPathStage(nn.Module):
    def __init__(self, feature_channels: dict[str, int], out_channels: int):
        """feature_channels must contain keys "16x" and "32x"""
        super().__init__()
        self.global_pool = nn.AdaptiveAvgPool2d(1)
        self.arm_16x = AttentionRefinementModule(feature_channels["16x"], out_channels)
        self.arm_32x = AttentionRefinementModule(feature_channels["32x"], out_channels)
        self.conv_16x = ConvNormAct(out_channels, out_channels, 3)
        self.conv_32x = ConvNormAct(out_channels, out_channels, 3)
        self.conv_global = ConvNormAct(feature_channels["32x"], out_channels, 1)

    def forward(self, feature_maps: dict[str, Tensor], output_size: list[int]):
        """feature_maps must contain keys "16x" and "32x"""
        feature_16x, feature_32x = feature_maps["16x"], feature_maps["32x"]

        global_out = self.global_pool(feature_32x)
        global_out = self.conv_global(global_out)

        out_32x = self.arm_32x(feature_32x) + global_out
        out_32x = F.interpolate(out_32x, feature_16x.shape[2:], mode="bilinear")
        out_32x = self.conv_32x(out_32x)

        out_16x = self.arm_16x(feature_16x) + out_32x
        out_16x = F.interpolate(out_16x, output_size, mode="bilinear")
        out_16x = self.conv_16x(out_16x)

        return out_32x, out_16x


class SpatialPath(nn.Sequential):
    def __init__(self, in_channels: int, out_channels: int) -> None:
        inter_channels = out_channels // 2
        super().__init__(
            ConvNormAct(in_channels, inter_channels, 7, 2),
            ConvNormAct(inter_channels, inter_channels, 3, 2),
            ConvNormAct(inter_channels, inter_channels, 3, 2),
            ConvNormAct(inter_channels, out_channels, 1, 1),
        )


class AttentionRefinementModule(nn.Module):
    def __init__(self, in_channels: int, out_channels: int) -> None:
        super().__init__()
        self.conv = ConvNormAct(in_channels, out_channels, 3, 1)
        self.attention = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Conv2d(out_channels, out_channels, 1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.Sigmoid(),
        )

    def forward(self, x: Tensor):
        features = self.conv(x)
        weight = self.attention(features)
        out = features * weight
        return out


class FeatureFusionModule(nn.Module):
    def __init__(self, in_channels: int, out_channels: int) -> None:
        super().__init__()
        self.conv = ConvNormAct(in_channels, out_channels, 1)
        self.attention = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Conv2d(out_channels, out_channels // 4, 1, bias=True),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels // 4, out_channels, 1, bias=True),
            nn.Sigmoid(),
        )

    def forward(self, x: Tensor):
        features = self.conv(x)
        weight = self.attention(features)
        out = features + features * weight
        return out


class ConvNormAct(nn.Sequential):
    def __init__(
        self, in_channels: int, out_channels: int, kernel_size: int, stride: int = 1
    ):
        super().__init__(
            nn.Conv2d(
                in_channels,
                out_channels,
                kernel_size,
                padding=kernel_size // 2,
                stride=stride,
                bias=False,
            ),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )


class Upscale(nn.Sequential):
    """interpolate tensors while keeping the same number of channels"""

    def __init__(self, in_channels: int, out_channels: int, factor=2):
        super().__init__(
            nn.Conv2d(in_channels, out_channels * factor * factor, 1),
            nn.PixelShuffle(factor),
        )


class BiSeNet_ResNet18_Weights(SegWeightsEnum):
    CITYSCAPES_FINE = SegWeights(
        "bisenet/bisenet_resnet18-cityscapes-512x1024-20250305.pth",
        CITYSCAPES_LABELS,
        "Trained on Cityscapes (fine) dataset",
    )
    DEFAULT = CITYSCAPES_FINE


@register_model(weights_enum=BiSeNet_ResNet18_Weights)
def bisenet_resnet18(
    num_classes: int | None = None,
    weights: BiSeNet_ResNet18_Weights | str | None = None,
    progress: bool = True,
    aux_loss: bool = False,
    weights_backbone: ResNet18_Weights | str | None = ResNet18_Weights.DEFAULT,
) -> nn.Module:
    weights_model = BiSeNet_ResNet18_Weights.resolve(weights)
    weights_model, weights_backbone, num_classes = _validate_weights_input(
        weights_model, weights_backbone, num_classes
    )

    backbone_model = resnet18(weights=weights_backbone, progress=progress)
    backbone = ResNetBackbone(backbone_model)
    replace_layer_name(backbone, {-2: "16x", -1: "32x"})

    channels = backbone.layer_channels()
    model = BiSeNet(num_classes, backbone, channels, use_aux=aux_loss)

    if weights_model is not None:
        state_dict = load_state_dict_from_url(weights_model.url, progress=progress)
        model.load_state_dict(state_dict)
    return model


@register_model()
def bisenet_resnet50(
    num_classes: int | None = None,
    weights: str | None = None,
    progress: bool = True,
    aux_loss: bool = False,
    weights_backbone: ResNet50_Weights | str | None = ResNet50_Weights.DEFAULT,
) -> nn.Module:
    if weights is not None:
        raise NotImplementedError("Weights is not supported yet")
    _, weights_backbone, num_classes = _validate_weights_input(
        None, weights_backbone, num_classes
    )

    backbone_model = resnet50(
        weights=weights_backbone,
        progress=progress,
        replace_stride_with_dilation=[False, True, True],
    )
    backbone = ResNetBackbone(backbone_model)
    replace_layer_name(backbone, {-2: "16x", -1: "32x"})

    channels = backbone.layer_channels()
    model = BiSeNet(num_classes, backbone, channels, use_aux=aux_loss)
    return model


@register_model()
def bisenet_xception(
    num_classes: int | None = None,
    weights: str | None = None,
    progress: bool = True,
    aux_loss: bool = False,
    weights_backbone: Xception_Weights | str | None = Xception_Weights.DEFAULT,
) -> nn.Module:
    """Using the original Xception as backbone

    The BiSeNet paper suggested using xception39 as backbone, but I can't seem
    to find its definition?
    """
    if weights is not None:
        raise NotImplementedError("Weights is not supported yet")
    _, weights_backbone, num_classes = _validate_weights_input(
        None, weights_backbone, num_classes
    )

    backbone_model = xception_original(weights=weights_backbone, progress=progress)
    backbone = XceptionBackbone(backbone_model)
    replace_layer_name(backbone, {-2: "16x", -1: "32x"})

    channels = backbone.layer_channels()
    model = BiSeNet(num_classes, backbone, channels, use_aux=aux_loss)
    return model
