import os, requests
from dotenv import load_dotenv
load_dotenv()

TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN")
IG_ID = os.getenv("INSTAGRAM_USER_ID")

def upload_to_catbox(image_bytes):
    r = requests.post(
        "https://catbox.moe/user/api.php",
        data={"reqtype": "fileupload"},
        files={"fileToUpload": ("photo.jpg", image_bytes, "image/jpeg")},
        timeout=30
    )
    return r.text.strip()

def post_carousel_to_instagram(image_bytes_list, caption):
    if not TOKEN or not IG_ID:
        return "INSTAGRAM_USER_ID / TOKEN .env e nei!"
    try:
        urls = []
        for b in image_bytes_list:
            url = upload_to_catbox(b)
            print("Uploaded:", url)
            urls.append(url)

        if len(urls) == 1:
            r = requests.post(f"https://graph.facebook.com/v21.0/{IG_ID}/media", data={
                "image_url": urls[0],
                "caption": caption,
                "access_token": TOKEN
            }).json()
            print("Create:", r)
            if "id" not in r:
                return f"Photo container banate parini: {r}"
            container_id = r["id"]
        else:
            children = []
            for u in urls:
                r = requests.post(f"https://graph.facebook.com/v21.0/{IG_ID}/media", data={
                    "image_url": u,
                    "is_carousel_item": "true",
                    "access_token": TOKEN
                }).json()
                if "id" not in r:
                    return f"Photo container banate parini: {r}"
                children.append(r["id"])
            r = requests.post(f"https://graph.facebook.com/v21.0/{IG_ID}/media", data={
                "media_type": "CAROUSEL",
                "children": ",".join(children),
                "caption": caption,
                "access_token": TOKEN
            }).json()
            if "id" not in r:
                return f"Carousel container banate parini: {r}"
            container_id = r["id"]

        r2 = requests.post(f"https://graph.facebook.com/v21.0/{IG_ID}/media_publish", data={
            "creation_id": container_id,
            "access_token": TOKEN
        }).json()
        print("Publish:", r2)
        if "id" in r2:
            return f"✅ Instagram e post hoye geche! Post ID: {r2['id']}"
        return f"Publish e problem: {r2}"
    except Exception as e:
        return f"Error: {e}"