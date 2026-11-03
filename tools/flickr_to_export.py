# /// script
# requires-python = ">=3.10"
# ///
"""Turn gallery-dl Flickr output (-j) into an export file for To Are.na.

Each gallery, album or group pool becomes one collection (one Are.na channel), photos in the
order Flickr lists them. gallery-dl finds Flickr's API key itself, so nothing else is needed.

    uv tool run gallery-dl -j -i urls.txt > flickr.json
    uv run tools/flickr_to_export.py flickr.json flickr-export.json

urls.txt takes gallery, album, group and user/favorites URLs. Add the resulting file on the
To Are.na page ("Add your export file").
"""
import argparse
import json
import sys
from datetime import datetime, timezone

FLICKR = "https://www.flickr.com"


def text(value):
    """Flickr wraps some strings as {"_content": "..."}."""
    if isinstance(value, dict):
        value = value.get("_content")
    return (str(value).strip() if value is not None else "") or None


def values(path):
    """Every JSON value in the file, also when gallery-dl runs several URLs back to back."""
    raw = open(path, encoding="utf-8").read()
    decoder, pos = json.JSONDecoder(), 0
    while True:
        while pos < len(raw) and raw[pos].isspace():
            pos += 1
        if pos >= len(raw):
            return
        value, pos = decoder.raw_decode(raw, pos)
        yield value


def photos(path):
    """gallery-dl -j lists [2, directory metadata] and [3, url, file metadata]; keep the files."""
    for value in values(path):
        for entry in value if isinstance(value, list) and value and isinstance(value[0], list) else [value]:
            if isinstance(entry, list) and len(entry) == 3 and entry[0] == 3 and isinstance(entry[2], dict):
                yield entry[2]


def collection_of(meta, user_name):
    """The gallery, album, group pool or user the photo was listed in."""
    gallery, album, group = (meta.get(k) or {} for k in ("gallery", "album", "group"))
    if gallery.get("gallery_id") or gallery.get("id"):
        gid = str(gallery.get("gallery_id") or gallery["id"])
        return f"gallery-{gid}", text(gallery.get("title")) or f"Gallery {gid}", text(gallery.get("description")), gallery.get("url")
    if album.get("id"):
        return f"album-{album['id']}", text(album.get("title")) or f"Album {album['id']}", text(album.get("description")), None
    if group.get("nsid"):
        alias = group.get("path_alias") or group["nsid"]
        return f"group-{group['nsid']}", text(group.get("groupname")) or alias, None, f"{FLICKR}/groups/{alias}/pool/"
    user = meta.get("user") or {}
    nsid = user.get("nsid") or "user"
    return f"user-{nsid}", f"Flickr · {user_name or user.get('username') or nsid}", None, None


def element_of(meta):
    owner = meta.get("owner") or {}
    owner_id = owner.get("path_alias") or owner.get("nsid")
    page = f"{FLICKR}/photos/{owner_id}/{meta['id']}/" if owner_id else None
    created = None
    if meta.get("dateupload"):
        created = datetime.fromtimestamp(int(meta["dateupload"]), timezone.utc).isoformat().replace("+00:00", "Z")
    author = None
    if owner.get("username") or owner_id:
        author = {
            "name": owner.get("username") or owner_id,
            "username": owner_id,
            "url": f"{FLICKR}/photos/{owner_id}/" if owner_id else None,
        }
    tags = meta.get("tags") or []
    description = text(meta.get("description"))
    if tags:
        description = "\n\n".join(filter(None, [description, "Tags: " + ", ".join(f"#{t}" for t in tags)]))
    return {
        "id": str(meta["id"]),
        "kind": "media",
        "createdAt": created,
        "url": page,
        "caption": "",
        "source": {"url": page, "author": author},
        "media": [
            {
                "type": "AnimatedImage" if meta["url"].lower().endswith(".gif") else "StaticImage",
                "url": meta["url"],
                "width": meta.get("width") or None,
                "height": meta.get("height") or None,
            }
        ],
        "title": text(meta.get("title")),
        "description": description,
        "alt": None,
        "brand": None,
        "text": None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", help="output of gallery-dl -j")
    parser.add_argument("output", help="export file to write")
    parser.add_argument("--user-channel-name", help="channel name for photos that come from a user's page or favorites")
    args = parser.parse_args()

    elements, collections, skipped = {}, {}, 0
    owner = None
    for meta in photos(args.input):
        url = meta.get("url") or ""
        if not url.startswith("https://") or meta.get("media") == "video" or "/video/" in url:
            skipped += 1  # videos give a player address, not a file Are.na can fetch
            continue
        key, name, description, source_url = collection_of(meta, args.user_channel_name)
        c = collections.setdefault(
            key,
            {
                "id": key,
                "name": name,
                "slug": None,
                "description": description or "",
                "isPrivate": False,
                "parentId": None,
                "system": False,
                "owner": (meta.get("user") or {}).get("username"),
                "cover": None,
                "expectedCount": None,
                "includesChildren": False,
                "url": source_url,
                "elementIds": [],
            },
        )
        owner = owner or meta.get("user")
        eid = str(meta["id"])
        elements.setdefault(eid, element_of(meta))
        if eid not in c["elementIds"]:
            c["elementIds"].append(eid)

    if not collections:
        sys.exit("No photos found in this file. Was it made with gallery-dl -j on Flickr URLs?")
    for c in collections.values():
        c["expectedCount"] = len(c["elementIds"])

    export = {
        "schema": "arena-import/1",
        "source": "flickr",
        "exportedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "user": {"id": (owner or {}).get("nsid", ""), "username": (owner or {}).get("username", "flickr"), "fullName": ""},
        "collections": list(collections.values()),
        "library": None,
        "elements": elements,
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(export, f, ensure_ascii=False)
    print(f"{len(collections)} collections, {len(elements)} photos" + (f", {skipped} skipped (videos or no usable URL)" if skipped else ""), file=sys.stderr)


if __name__ == "__main__":
    main()
