from dependency_modules.rewarding.utils import base64_to_pil_image, pil_image_to_base64
import imagehash
from PIL import Image
from typing import List


def matching_image(miner_image: Image.Image, validator_image: Image.Image) -> bool:
    miner_hash = imagehash.phash(miner_image, hash_size=8)
    validator_hash = imagehash.phash(validator_image, hash_size=8)
    print("Hamming Distance:", miner_hash - validator_hash, flush=True)
    return (miner_hash - validator_hash) <= 2


def infer_hash(validator_image: Image.Image, batched_miner_images: List[str]):
    rewards = []
    for miner_image in batched_miner_images:
        miner_image = base64_to_pil_image(miner_image)
        validator_image = base64_to_pil_image(pil_image_to_base64(validator_image))
        if miner_image is None:
            reward = False
        else:
            reward = matching_image(miner_image, validator_image)
        rewards.append(reward)
    print(rewards, flush=True)
    return rewards
