from pathlib import Path
from typing import Any, Literal

from torch.utils.data import Dataset
from torchvision.io import ImageReadMode, decode_image
from torchvision.transforms.v2 import Transform

from .dataset_registry import DatasetMeta, register_dataset

# fmt: off
ADE20K_LABELS = (
    'background', 'wall', 'building, edifice', 'sky', 'floor, flooring', 'tree',
    'ceiling', 'road, route', 'bed ', 'windowpane, window ', 'grass', 'cabinet',
    'sidewalk, pavement', 'person, individual, someone, somebody, mortal, soul',
    'earth, ground', 'door, double door', 'table', 'mountain, mount',
    'plant, flora, plant life', 'curtain, drape, drapery, mantle, pall', 'chair',
    'car, auto, automobile, machine, motorcar', 'water', 'painting, picture',
    'sofa, couch, lounge', 'shelf', 'house', 'sea', 'mirror',
    'rug, carpet, carpeting', 'field', 'armchair', 'seat', 'fence, fencing',
    'desk', 'rock, stone', 'wardrobe, closet, press', 'lamp',
    'bathtub, bathing tub, bath, tub', 'railing, rail', 'cushion',
    'base, pedestal, stand', 'box', 'column, pillar', 'signboard, sign',
    'chest of drawers, chest, bureau, dresser', 'counter', 'sand', 'sink',
    'skyscraper', 'fireplace, hearth, open fireplace', 'refrigerator, icebox',
    'grandstand, covered stand', 'path', 'stairs, steps', 'runway',
    'case, display case, showcase, vitrine',
    'pool table, billiard table, snooker table', 'pillow', 'screen door, screen',
    'stairway, staircase', 'river', 'bridge, span', 'bookcase', 'blind, screen',
    'coffee table, cocktail table',
    'toilet, can, commode, crapper, pot, potty, stool, throne', 'flower', 'book',
    'hill', 'bench', 'countertop',
    'stove, kitchen stove, range, kitchen range, cooking stove', 'palm, palm tree',
    'kitchen island',
    'computer, computing machine, computing device, data processor, electronic '
    'computer, information processing system',
    'swivel chair', 'boat', 'bar', 'arcade machine',
    'hovel, hut, hutch, shack, shanty',
    'bus, autobus, coach, charabanc, double-decker, jitney, motorbus, motorcoach, '
    'omnibus, passenger vehicle',
    'towel', 'light, light source', 'truck, motortruck', 'tower',
    'chandelier, pendant, pendent', 'awning, sunshade, sunblind',
    'streetlight, street lamp', 'booth, cubicle, stall, kiosk',
    'television receiver, television, television set, tv, tv set, idiot box, boob '
    'tube, telly, goggle box',
    'airplane, aeroplane, plane', 'dirt track',
    'apparel, wearing apparel, dress, clothes', 'pole', 'land, ground, soil',
    'bannister, banister, balustrade, balusters, handrail',
    'escalator, moving staircase, moving stairway',
    'ottoman, pouf, pouffe, puff, hassock', 'bottle', 'buffet, counter, sideboard',
    'poster, posting, placard, notice, bill, card', 'stage', 'van', 'ship',
    'fountain', 'conveyer belt, conveyor belt, conveyer, conveyor, transporter',
    'canopy', 'washer, automatic washer, washing machine', 'plaything, toy',
    'swimming pool, swimming bath, natatorium', 'stool', 'barrel, cask',
    'basket, handbasket', 'waterfall, falls', 'tent, collapsible shelter', 'bag',
    'minibike, motorbike', 'cradle', 'oven', 'ball', 'food, solid food',
    'step, stair', 'tank, storage tank', 'trade name, brand name, brand, marque',
    'microwave, microwave oven', 'pot, flowerpot',
    'animal, animate being, beast, brute, creature, fauna',
    'bicycle, bike, wheel, cycle ', 'lake',
    'dishwasher, dish washer, dishwashing machine',
    'screen, silver screen, projection screen', 'blanket, cover', 'sculpture',
    'hood, exhaust hood', 'sconce', 'vase',
    'traffic light, traffic signal, stoplight', 'tray',
    'ashcan, trash can, garbage can, wastebin, ash bin, ash-bin, ashbin, dustbin, '
    'trash barrel, trash bin',
    'fan', 'pier, wharf, wharfage, dock', 'crt screen', 'plate',
    'monitor, monitoring device', 'bulletin board, notice board', 'shower',
    'radiator', 'glass, drinking glass', 'clock', 'flag'
)
# fmt: on


@register_dataset(
    {"split": "training"},
    {"split": "validation"},
    meta=DatasetMeta.default(151, labels=ADE20K_LABELS),
)
class ADE20K(Dataset):
    """[ADE20K](https://ade20k.csail.mit.edu/) Dataset"""

    def __init__(
        self,
        root: Path | str,
        split: Literal["training", "validation"],
        transforms: Transform | None = None,
    ) -> None:
        self.transforms = transforms

        root_path = Path(root)
        image_folder = root_path / "images" / split
        self.image_files = list(image_folder.glob("*.jpg"))
        target_folder = root_path / "annotations" / split
        self.target_files = list(target_folder.glob("*.png"))

    def __len__(self):
        return len(self.image_files)

    def __getitem__(self, index) -> Any:
        image = decode_image(self.image_files[index], ImageReadMode.RGB)
        target = decode_image(self.target_files[index])
        if self.transforms is not None:
            image, target = self.transforms(image, target)
        return image, target
