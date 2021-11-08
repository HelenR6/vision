import os
from abc import ABC, abstractmethod
from glob import glob
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from ..io.image import _read_png_16
from .utils import verify_str_arg
from .vision import VisionDataset


__all__ = (
    "KittiFlow",
    "Sintel",
    "FlyingChairs",
)


class FlowDataset(ABC, VisionDataset):
    # Some datasets like Kitti have a built-in valid mask, indicating which flow values are valid
    # For those we return (img1, img2, flow, valid), and for the rest we return (img1, img2, flow),
    # and it's up to whatever consumes the dataset to decide what `valid` should be.
    _has_builtin_flow_mask = False

    def __init__(self, root, transforms=None):

        super().__init__(root=root)
        self.transforms = transforms

        self._flow_list = []
        self._image_list = []

    def _read_img(self, file_name):
        return Image.open(file_name)

    @abstractmethod
    def _read_flow(self, file_name):
        # Return the flow or a tuple with the flow and the valid mask if _has_builtin_flow_mask is True
        pass

    def __getitem__(self, index):

        img1 = self._read_img(self._image_list[index][0])
        img2 = self._read_img(self._image_list[index][1])

        if self._flow_list:  # it will be empty for some dataset when split="test"
            flow = self._read_flow(self._flow_list[index])
            if self._has_builtin_flow_mask:
                flow, valid = flow
            else:
                valid = None
        else:
            flow = valid = None

        if self.transforms is not None:
            img1, img2, flow, valid = self.transforms(img1, img2, flow, valid)

        if self._has_builtin_flow_mask:
            return img1, img2, flow, valid
        else:
            return img1, img2, flow

    def __len__(self):
        return len(self._image_list)


class Sintel(FlowDataset):
    """`Sintel <http://sintel.is.tue.mpg.de/>`_ Dataset for optical flow.

    The dataset is expected to have the following structure: ::

        root
            Sintel
                testing
                    clean
                        scene_1
                        scene_2
                        ...
                    final
                        scene_1
                        scene_2
                        ...
                training
                    clean
                        scene_1
                        scene_2
                        ...
                    final
                        scene_1
                        scene_2
                        ...
                    flow
                        scene_1
                        scene_2
                        ...

    Args:
        root (string): Root directory of the Sintel Dataset.
        split (string, optional): The dataset split, either "train" (default) or "test"
        pass_name (string, optional): The pass to use, either "clean" (default) or "final". See link above for
            details on the different passes.
        transforms (callable, optional): A function/transform that takes in
            ``img1, img2, flow, valid`` and returns a transformed version.
            ``valid`` is expected for consistency with other datasets which
            return a built-in valid mask, such as :class:`~torchvision.datasets.KittiFlow`.
    """

    def __init__(self, root, split="train", pass_name="clean", transforms=None):
        super().__init__(root=root, transforms=transforms)

        verify_str_arg(split, "split", valid_values=("train", "test"))
        verify_str_arg(pass_name, "pass_name", valid_values=("clean", "final"))

        root = Path(root) / "Sintel"

        split_dir = "training" if split == "train" else split
        image_root = root / split_dir / pass_name
        flow_root = root / "training" / "flow"

        for scene in os.listdir(image_root):
            image_list = sorted(glob(str(image_root / scene / "*.png")))
            for i in range(len(image_list) - 1):
                self._image_list += [[image_list[i], image_list[i + 1]]]

            if split == "train":
                self._flow_list += sorted(glob(str(flow_root / scene / "*.flo")))

    def __getitem__(self, index):
        """Return example at given index.

        Args:
            index(int): The index of the example to retrieve

        Returns:
            tuple: If ``split="train"`` a 3-tuple with ``(img1, img2, flow)``.
            The flow is a numpy array of shape (2, H, W) and the images are PIL images. If `split="test"`, a
            3-tuple with ``(img1, img2, None)`` is returned.
        """
        return super().__getitem__(index)

    def _read_flow(self, file_name):
        return _read_flo(file_name)


class KittiFlow(FlowDataset):
    """`KITTI <http://www.cvlibs.net/datasets/kitti/eval_scene_flow.php?benchmark=flow>`__ dataset for optical flow (2015).

    The dataset is expected to have the following structure: ::

        root
            Kitti
                testing
                    image_2
                training
                    image_2
                    flow_occ

    Args:
        root (string): Root directory of the KittiFlow Dataset.
        split (string, optional): The dataset split, either "train" (default) or "test"
        transforms (callable, optional): A function/transform that takes in
            ``img1, img2, flow, valid`` and returns a transformed version.
    """

    _has_builtin_flow_mask = True

    def __init__(self, root, split="train", transforms=None):
        super().__init__(root=root, transforms=transforms)

        verify_str_arg(split, "split", valid_values=("train", "test"))

        root = Path(root) / "Kitti" / (split + "ing")
        images1 = sorted(glob(str(root / "image_2" / "*_10.png")))
        images2 = sorted(glob(str(root / "image_2" / "*_11.png")))

        if not images1 or not images2:
            raise FileNotFoundError(
                "Could not find the Kitti flow images. Please make sure the directory structure is correct."
            )

        for img1, img2 in zip(images1, images2):
            self._image_list += [[img1, img2]]

        if split == "train":
            self._flow_list = sorted(glob(str(root / "flow_occ" / "*_10.png")))

    def __getitem__(self, index):
        """Return example at given index.

        Args:
            index(int): The index of the example to retrieve

        Returns:
            tuple: If ``split="train"`` a 4-tuple with ``(img1, img2, flow,
            valid)`` where ``valid`` is a numpy boolean mask of shape (H, W)
            indicating which flow values are valid. The flow is a numpy array of
            shape (2, H, W) and the images are PIL images. If `split="test"`, a
            4-tuple with ``(img1, img2, None, None)`` is returned.
        """
        return super().__getitem__(index)

    def _read_flow(self, file_name):
        return _read_16bits_png_with_flow_and_valid_mask(file_name)


class FlyingChairs(FlowDataset):
    """`FlyingChairs <https://lmb.informatik.uni-freiburg.de/resources/datasets/FlyingChairs.en.html#flyingchairs>`_ Dataset for optical flow.

    You will also need to download the FlyingChairs_train_val.txt file from the dataset page.

    The dataset is expected to have the following structure: ::

        root
            FlyingChairs
                data
                    00001_flow.flo
                    00001_img1.ppm
                    00001_img2.ppm
                    ...
                FlyingChairs_train_val.txt


    Args:
        root (string): Root directory of the FlyingChairs Dataset.
        split (string, optional): The dataset split, either "train" (default) or "val"
        transforms (callable, optional): A function/transform that takes in
            ``img1, img2, flow, valid`` and returns a transformed version.
            ``valid`` is expected for consistency with other datasets which
            return a built-in valid mask, such as :class:`~torchvision.datasets.KittiFlow`.
    """

    def __init__(self, root, split="train", transforms=None):
        super().__init__(root=root, transforms=transforms)

        verify_str_arg(split, "split", valid_values=("train", "val"))

        root = Path(root) / "FlyingChairs"
        images = sorted(glob(str(root / "data" / "*.ppm")))
        flows = sorted(glob(str(root / "data" / "*.flo")))

        split_file_name = "FlyingChairs_train_val.txt"

        if not os.path.exists(root / split_file_name):
            raise FileNotFoundError(
                "The FlyingChairs_train_val.txt file was not found - please download it from the dataset page (see docstring)."
            )

        split_list = np.loadtxt(str(root / split_file_name), dtype=np.int32)
        for i in range(len(flows)):
            split_id = split_list[i]
            if (split == "train" and split_id == 1) or (split == "val" and split_id == 2):
                self._flow_list += [flows[i]]
                self._image_list += [[images[2 * i], images[2 * i + 1]]]

    def __getitem__(self, index):
        """Return example at given index.

        Args:
            index(int): The index of the example to retrieve

        Returns:
            tuple: A 3-tuple with ``(img1, img2, flow)``.
            The flow is a numpy array of shape (2, H, W) and the images are PIL images.
        """
        return super().__getitem__(index)

    def _read_flow(self, file_name):
        return _read_flo(file_name)


def _read_flo(file_name):
    """Read .flo file in Middlebury format"""
    # Code adapted from:
    # http://stackoverflow.com/questions/28013200/reading-middlebury-flow-files-with-python-bytes-array-numpy
    # WARNING: this will work on little-endian architectures (eg Intel x86) only!
    with open(file_name, "rb") as f:
        magic = np.fromfile(f, np.float32, count=1)
        if 202021.25 != magic:
            raise ValueError("Magic number incorrect. Invalid .flo file")

        w = int(np.fromfile(f, np.int32, count=1))
        h = int(np.fromfile(f, np.int32, count=1))
        data = np.fromfile(f, np.float32, count=2 * w * h)
        return data.reshape(2, h, w)


def _read_16bits_png_with_flow_and_valid_mask(file_name):

    flow_and_valid = _read_png_16(file_name).to(torch.float32)
    flow, valid = flow_and_valid[:2, :, :], flow_and_valid[2, :, :]
    flow = (flow - 2 ** 15) / 64  # This conversion is explained somewhere on the kitti archive

    # For consistency with other datasets, we convert to numpy
    return flow.numpy(), valid.numpy()
