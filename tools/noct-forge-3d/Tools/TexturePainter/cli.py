import argparse
import json
import sys
import os

from .painter import TexturePainter

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _face_line(name, face):
    info = face.uv_info
    if info.get("owner"):
        return f"  - {name}: shared; paint owner {'.'.join(info['owner'])}"
    return (f"  - {name}: {face.width}x{face.height} at ({info['x']},{info['y']}); "
            f"flip=({info['flip_x']},{info['flip_y']}); rot={info['rotation']}; "
            f"layout={info['layout']}")


def main():
    parser = argparse.ArgumentParser(description="Blockbench Procedural Texture Painter CLI")
    parser.add_argument("bbmodel", help="Caminho para o arquivo .bbmodel")
    parser.add_argument("--info", action="store_true", help="Show compact element information")
    parser.add_argument("--element", help="Show UV faces for one element")
    parser.add_argument("--face", help="Show one face; requires --element")
    parser.add_argument("--tag", help="Filter elements by one explicit model_as_code tag")
    parser.add_argument("--limit", type=int, default=12, help="Maximum compact element examples")
    parser.add_argument("--quiet", action="store_true", help="Validate without the summary header")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable inspection data")
    
    args = parser.parse_args()
    if args.face and not args.element:
        parser.error("--face requires --element")
    if args.limit <= 0:
        parser.error("--limit must be positive")
    
    if not os.path.exists(args.bbmodel):
        print(f"Error: file {args.bbmodel} not found.")
        sys.exit(1)
        
    painter = TexturePainter.from_bbmodel(args.bbmodel)
    elements = list(painter.elements.values())
    if args.tag:
        elements = [element for element in elements if args.tag in element.tags]
    if args.element:
        elements = [element for element in elements if element.name == args.element]
        if not elements:
            print(f"Error: element {args.element!r} not found in current filters", file=sys.stderr)
            sys.exit(1)

    if args.json:
        payload = {
            "model": args.bbmodel,
            "resolution": [painter.width, painter.height],
            "element_count": len(painter.elements),
            "elements": [],
        }
        for element in elements[:args.limit]:
            item = {
                "name": element.name,
                "kind": element.element_data["kind"],
                "tags": list(element.tags),
                "face_count": len(element.faces),
            }
            if args.element:
                faces = element.faces.items()
                if args.face:
                    faces = [(name, face) for name, face in faces if name == args.face]
                    if not faces:
                        parser.error(f"face {args.face!r} not found on {element.name!r}")
                item["faces"] = {name: face.uv_info for name, face in faces}
            payload["elements"].append(item)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if not args.quiet:
        print(f"Model loaded: {args.bbmodel}")
        print(f"Texture resolution: {painter.width}x{painter.height}")
        print(f"Total elements: {len(painter.elements)}")

    if args.info or args.element or args.tag:
        shown = elements[:args.limit]
        for element in shown:
            tags = f" tags={list(element.tags)}" if element.tags else ""
            print(f"[{element.name}] {element.element_data['kind']}; "
                  f"{len(element.faces)} faces{tags}")
            if args.element:
                faces = element.faces.items()
                if args.face:
                    faces = [(name, face) for name, face in faces if name == args.face]
                    if not faces:
                        print(f"Error: face {args.face!r} not found on {element.name!r}", file=sys.stderr)
                        sys.exit(1)
                for name, face in faces:
                    print(_face_line(name, face))
        remaining = len(elements) - len(shown)
        if remaining:
            print(f"... {remaining} more elements; use --element, --tag, or a larger --limit")

if __name__ == "__main__":
    main()
