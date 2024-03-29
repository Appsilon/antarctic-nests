import itertools
import pandas as pd
import yaml
from pathlib import Path
from config import settings


class YoloDataset:

    """
    Data model for a YOLOv6 dataset. Creates expected folder structure and yaml file that YOLOv6 expects.
    """

    path: Path
    train_dir: str = "train"
    val_dir: str = "val"
    image_dir: str = "images"
    label_dir: str = "labels"
    image_fmt: str = ".jpg"
    is_coco: bool = False
    class_names: list[str] = ["nest"]
    num_classes: int = 1
    yaml_file = "dataset.yaml"
    metadata_file = "metadata.csv"

    def __init__(self, path: Path, update_yaml: bool = False, **kwargs):

        self.path = path

        if not self.path.exists():
            raise NotADirectoryError()

        # Creating necessary folder structure
        for subdir, subsubdir in itertools.product((self.image_dir, self.label_dir), (self.train_dir, self.val_dir)):
            (self.path / subdir / subsubdir).mkdir(exist_ok=True, parents=True)

        # Creating yaml file if does not already exist
        if update_yaml or not (self.path / self.yaml_file).exists():
            self.to_yaml()

    def purge(self, empty_imgs_frac: float = 0.5, blank_pixel_threshold: float = 1., sample_per_image: bool = True, trial: bool = True, seed: int = 42):

        # TODO: Hardcode columns, these should be defined somewhere
        df_orig = pd.read_csv(self.path / self.metadata_file)

        # Removing blank images immediately from both train and val
        df = df_orig[df_orig["pct_black"] < blank_pixel_threshold].copy()
        df_train = df[df["split"] == "train"].copy()
        df_valid = df[df["split"] == "val"].copy()

        total_with_objects = (df_train["num_objects"] > 0).sum()
        n_empty = int(2 * total_with_objects * empty_imgs_frac)

        print(
            f"Total images: train {df_orig[df_orig['split'] == 'train'].shape[0]}, val {df_orig[df_orig['split'] == 'val'].shape[0]}",
            f"Total after removing blanks: train {df_train.shape[0]}, val {df_valid.shape[0]}",
            f"Total train images with objects: {total_with_objects}",
            f"Keeping {n_empty} empty train images (pct_empty_imgs = {empty_imgs_frac})",
            sep="\n"
        )

        df_empty = df_train[df_train["num_objects"] == 0].copy()
        
        if sample_per_image:
            total_tifs = df_empty["tif_orig_name"].nunique()
            df_empty = df_empty\
                .groupby(by="tif_orig_name", group_keys=False)\
                .apply(lambda x: x.sample(min(len(x), int(n_empty / total_tifs)), random_state=seed))
        
        # Will also downsample above again if necessary
        df_empty = df_empty.sample(n=n_empty, random_state=seed) if df_empty.shape[0] > n_empty else df_empty

        # Keeping non-empty images, sampled empty images, and validation images
        df_keep = pd.concat([df_train[df_train["num_objects"] > 0], df_empty, df_valid]).sort_index()

        df_purge = df_orig.loc[df_orig.index.difference(df_keep.index)].copy()

        # Delete files in df_purge
        for _, row in df_purge.iterrows():

            print(f"Deleting: {row['img_path']}")
            if not trial:
                (self.path / row["img_path"]).unlink()
                (self.path / row["label_path"]).unlink()
        
        if trial:
            print(f"NOTE: Run in trial mode, no files were deleted")
        else:
            # Replace metadata file with kept files only
            self.write_metadata(df_keep)

    def to_yaml(self):
        
        yaml_data = {
                "is_coco": self.is_coco, 
                "names": self.class_names, 
                "nc": self.num_classes, 
                "train": str(self.path / self.image_dir / self.train_dir), 
                "val": str(self.path / self.image_dir / self.val_dir)
            }

        with open(self.path / self.yaml_file, "w") as f:
            
            yaml.dump(yaml_data, f)

    def write_metadata(self, df: pd.DataFrame):

        # TODO: Hardcode columns, these should be defined somewhere
        df["label_path"] = df["label_path"].apply(lambda x: Path(x).relative_to(self.path) if Path(x).is_relative_to(self.path) else x)
        df["img_path"] = df["img_path"].apply(lambda x: Path(x).relative_to(self.path) if Path(x).is_relative_to(self.path) else x)
        df.to_csv(self.path / self.metadata_file, index=False)


def init_from_data_folder(data_path: Path = settings.data_path):
    """
    Initialise all datasets within the data path.
    Recursively searches for directories with both an image_dir and label_dir (as defined by YoloDataset),
    creates the expected folder structure and a yaml file with the correct paths.
    """
    for d in data_path.rglob("*"):

        if d.stem == "lost+found":
            continue
        
        if d.is_dir() and (d / YoloDataset.image_dir).exists() and (d / YoloDataset.label_dir).exists():
            print(f"Initialising YOLO dataset: {d.relative_to(data_path)}")
            YoloDataset(d, update_yaml=True)


if __name__ == "__main__":
    
    init_from_data_folder()