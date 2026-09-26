"""
L2CS-Net model definition (L2CS layer).

Vendored from https://github.com/Ahmednull/L2CS-Net (MIT licensed), file
l2cs/model.py, by Abdelrahman et al. "L2CS-Net: Transfer Learning From L2CS
to Gaze Estimation" (ECCV 2020).

Vendored rather than `pip install l2cs` because that package hard-depends on
`face_detection` (RetinaFace, a Cython extension needing a compiler) plus
matplotlib/pandas we don't use. The model itself is only this one class; we
get the ResNet Bottleneck from torchvision and detect/crop faces with the
MediaPipe FaceLandmarker already used elsewhere in this pipeline.

Architecture is unchanged: ResNet50 trunk, two 90-bin classification heads
(fc_yaw_gaze / fc_pitch_gaze) whose softmax expectation is decoded to a
continuous angle. Gaze360 bin width is 4 degrees over [-180, 180].
"""

from __future__ import annotations

import math

import torch
import torch.nn as nn
import torchvision

NUM_BINS = 90
BIN_WIDTH_DEG = 4.0
ANGLE_RANGE_DEG = 180.0


class L2CS(nn.Module):
    def __init__(self, block, layers, num_bins):
        self.inplanes = 64
        super().__init__()
        self.conv1 = nn.Conv2d(3, 64, kernel_size=7, stride=2, padding=3, bias=False)
        self.bn1 = nn.BatchNorm2d(64)
        self.relu = nn.ReLU(inplace=True)
        self.maxpool = nn.MaxPool2d(kernel_size=3, stride=2, padding=1)
        self.layer1 = self._make_layer(block, 64, layers[0])
        self.layer2 = self._make_layer(block, 128, layers[1], stride=2)
        self.layer3 = self._make_layer(block, 256, layers[2], stride=2)
        self.layer4 = self._make_layer(block, 512, layers[3], stride=2)
        self.avgpool = nn.AdaptiveAvgPool2d((1, 1))

        self.fc_yaw_gaze = nn.Linear(512 * block.expansion, num_bins)
        self.fc_pitch_gaze = nn.Linear(512 * block.expansion, num_bins)

        # Vestigial layer from previous experiments; present in the released
        # checkpoint's state_dict, so it has to exist to load it.
        self.fc_finetune = nn.Linear(512 * block.expansion + 3, 3)

        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                n = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
                m.weight.data.normal_(0, math.sqrt(2.0 / n))
            elif isinstance(m, nn.BatchNorm2d):
                m.weight.data.fill_(1)
                m.bias.data.zero_()

    def _make_layer(self, block, planes, blocks, stride=1):
        downsample = None
        if stride != 1 or self.inplanes != planes * block.expansion:
            downsample = nn.Sequential(
                nn.Conv2d(
                    self.inplanes,
                    planes * block.expansion,
                    kernel_size=1,
                    stride=stride,
                    bias=False,
                ),
                nn.BatchNorm2d(planes * block.expansion),
            )

        layers = [block(self.inplanes, planes, stride, downsample)]
        self.inplanes = planes * block.expansion
        for _ in range(1, blocks):
            layers.append(block(self.inplanes, planes))

        return nn.Sequential(*layers)

    def forward(self, x):
        x = self.conv1(x)
        x = self.bn1(x)
        x = self.relu(x)
        x = self.maxpool(x)

        x = self.layer1(x)
        x = self.layer2(x)
        x = self.layer3(x)
        x = self.layer4(x)
        x = self.avgpool(x)
        x = x.view(x.size(0), -1)

        pre_yaw_gaze = self.fc_yaw_gaze(x)
        pre_pitch_gaze = self.fc_pitch_gaze(x)
        return pre_yaw_gaze, pre_pitch_gaze


def build_l2cs_resnet50(num_bins: int = NUM_BINS) -> L2CS:
    return L2CS(torchvision.models.resnet.Bottleneck, [3, 4, 6, 3], num_bins)


def load_l2cs_resnet50(weights_path: str, device: str = "cpu") -> L2CS:
    model = build_l2cs_resnet50()
    state_dict = torch.load(weights_path, map_location=device, weights_only=False)
    model.load_state_dict(state_dict)
    model.to(device)
    model.eval()
    return model


def decode_angles(yaw_logits: "torch.Tensor", pitch_logits: "torch.Tensor") -> "tuple[torch.Tensor, torch.Tensor]":
    """
    Turns the two 90-bin classification heads into continuous angles in
    degrees via the softmax expectation, matching the official inference code:
        angle = sum(softmax(logits) * [0..89]) * 4 - 180
    """
    idx = torch.arange(NUM_BINS, dtype=torch.float32, device=yaw_logits.device)
    yaw = (torch.softmax(yaw_logits, dim=1) * idx).sum(dim=1) * BIN_WIDTH_DEG - ANGLE_RANGE_DEG
    pitch = (torch.softmax(pitch_logits, dim=1) * idx).sum(dim=1) * BIN_WIDTH_DEG - ANGLE_RANGE_DEG
    return yaw, pitch
