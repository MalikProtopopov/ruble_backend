"""Upload real mock media (docs/mocks) to local MinIO and wire URLs into the DB.

- creates the `porubly` bucket (public-read) on the local MinIO
- uploads a feed video per campaign + generates a first-frame JPEG thumbnail (ffmpeg)
- uploads a thanks video/audio and points thanks_contents at it
- repoints media_assets rows to real uploaded objects
Run from backend/ with S3_ENDPOINT_URL=http://localhost:9000 and DATABASE_URL set.
"""
import asyncio, json, os, subprocess, tempfile, uuid

import boto3
from botocore.client import Config as BotoConfig
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings

MOCKS = "/Users/mak/fondback/docs/mocks"
PUB = settings.S3_PUBLIC_URL.rstrip("/")          # http://localhost:8000/media
BUCKET = settings.S3_BUCKET                        # porubly

s3 = boto3.client(
    "s3", endpoint_url=settings.S3_ENDPOINT_URL,
    aws_access_key_id=settings.S3_ACCESS_KEY, aws_secret_access_key=settings.S3_SECRET_KEY,
    config=BotoConfig(signature_version="s3v4"), region_name="us-east-1",
)

# campaign title -> feed video file
CAMPAIGN_VIDEOS = {
    "Лечение Маши": "feed/Девочка играет.mp4",
    "Тёплые вещи к зиме": "feed/Игрушки в детские дома.mp4",
    "Постоянная помощь фонду": "feed/Волонтер за работой.mp4",
    "Приостановленный сбор": "feed/Готовка блюд бездомных.mp4",
    "Завершённый сбор": "feed/Стоительство домов для нуждающихся и пострадавших после наводнений.mp4",
    "Архивный сбор": "feed/Волонтер Красный крест.mp4",
    "Черновик сбора": "feed/Мама играет с ребенком.mp4",
}
THANKS_VIDEO = "thanks/videoThanks0.mp4"
THANKS_AUDIO = "thanks/Благодарность мамы.mp3"


def ensure_bucket():
    try:
        s3.head_bucket(Bucket=BUCKET)
    except Exception:
        s3.create_bucket(Bucket=BUCKET)
    policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow", "Principal": {"AWS": ["*"]},
            "Action": ["s3:GetObject"], "Resource": [f"arn:aws:s3:::{BUCKET}/*"],
        }],
    }
    s3.put_bucket_policy(Bucket=BUCKET, Policy=json.dumps(policy))


def upload(local_path, key, content_type):
    s3.upload_file(local_path, BUCKET, key, ExtraArgs={"ContentType": content_type})
    return f"{PUB}/{key}"


def make_thumb(video_path):
    out = os.path.join(tempfile.gettempdir(), f"thumb_{uuid.uuid4().hex}.jpg")
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-ss", "0", "-i", video_path,
         "-frames:v", "1", "-q:v", "3", "-vf", "scale='min(1280,iw)':-2", out],
        check=True, timeout=60,
    )
    return out


async def main():
    ensure_bucket()
    print(f"bucket {BUCKET} ready")

    engine = create_async_engine(settings.DATABASE_URL, echo=False)

    # campaigns: video + thumbnail
    cam_updates = []
    for i, (title, rel) in enumerate(CAMPAIGN_VIDEOS.items()):
        src = os.path.join(MOCKS, rel)
        vkey = f"videos/campaign_{i}.mp4"
        vurl = upload(src, vkey, "video/mp4")
        thumb = make_thumb(src)
        tkey = f"thumbnails/campaign_{i}.jpg"
        turl = upload(thumb, tkey, "image/jpeg")
        os.remove(thumb)
        cam_updates.append((title, vurl, turl))
        print(f"  ✓ {title}: video+thumb")

    # thanks media
    tv_url = upload(os.path.join(MOCKS, THANKS_VIDEO), "thanks/video0.mp4", "video/mp4")
    ta_url = upload(os.path.join(MOCKS, THANKS_AUDIO), "thanks/audio0.mp3", "audio/mpeg")
    print("  ✓ thanks video + audio")

    async with engine.begin() as conn:
        for title, vurl, turl in cam_updates:
            await conn.execute(
                text("UPDATE campaigns SET video_url=:v, thumbnail_url=:t, updated_at=now() WHERE title=:title"),
                {"v": vurl, "t": turl, "title": title},
            )
        # existing thanks row (video) -> real video; add an audio thanks for the completed campaign
        await conn.execute(text("UPDATE thanks_contents SET media_url=:u WHERE type='video'"), {"u": tv_url})
        cc = (await conn.execute(text("SELECT id FROM campaigns WHERE title='Завершённый сбор'"))).scalar()
        await conn.execute(text("""
            INSERT INTO thanks_contents (id, campaign_id, type, media_url, title, description, created_at)
            VALUES (gen_random_uuid(), :cid, 'audio', :u, 'Аудио-благодарность', 'Спасибо от мамы', now())
        """), {"cid": cc, "u": ta_url})
        # repoint media_assets to real objects (image=a thumbnail, video, audio)
        img_url = cam_updates[0][2]  # first thumbnail jpg
        await conn.execute(text("UPDATE media_assets SET public_url=:u, s3_key='thumbnails/campaign_0.jpg' WHERE type='image'"), {"u": img_url})
        await conn.execute(text("UPDATE media_assets SET public_url=:u, s3_key='videos/campaign_0.mp4' WHERE type='video'"), {"u": cam_updates[0][1]})
        await conn.execute(text("UPDATE media_assets SET public_url=:u, s3_key='thanks/audio0.mp3' WHERE type='audio'"), {"u": ta_url})

    await engine.dispose()
    print("MEDIA_SEED_OK")


if __name__ == "__main__":
    asyncio.run(main())
