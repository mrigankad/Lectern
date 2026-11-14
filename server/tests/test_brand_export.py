"""PDF / PNG / notes export and brand kits (U09): extraction from a generated .potx, rules, apply, export."""
from __future__ import annotations

import copy
import io
import re
import zipfile
from pathlib import Path

import pypdfium2 as pdfium
from fastapi.testclient import TestClient
from PIL import Image
from pptx import Presentation
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.oxml.ns import qn
from pptx.util import Emu

from lectern.brand.extract import PRESENTATION_CT, TEMPLATE_CT
from lectern.engine.place import place_deck
from lectern.export.pdf import build_pdf
from lectern.schema import Theme

from . import samples
from .conftest import build_deck

A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def make_potx() -> bytes:
    """A small template: green/orange scheme, Georgia headings, Verdana body, a logo on the master."""
    prs = Presentation()
    prs.slide_width, prs.slide_height = Emu(12192000), Emu(6858000)
    master = prs.slide_masters[0]
    logo = io.BytesIO()
    Image.new("RGB", (200, 80), "#0B6E4F").save(logo, format="PNG")
    logo.seek(0)
    sample = prs.slides.add_slide(prs.slide_layouts[0])
    sample.shapes.title.text = "Sample slide that should be dropped"
    picture = sample.shapes.add_picture(logo, Emu(10500000), Emu(200000), Emu(1270000), Emu(508000))
    # python-pptx cannot add pictures to a master directly: move the picture's XML and image part over
    blip = picture._element.blipFill.blip
    image_part = sample.part.related_part(blip.rEmbed)
    blip.set(qn("r:embed"), master.part.relate_to(image_part, RT.IMAGE))
    master.shapes._spTree.append(copy.deepcopy(picture._element))
    buffer = io.BytesIO()
    prs.save(buffer)
    src = zipfile.ZipFile(io.BytesIO(buffer.getvalue()))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            blob = src.read(item.filename)
            if item.filename == "[Content_Types].xml":
                blob = blob.replace(PRESENTATION_CT, TEMPLATE_CT)
            if item.filename.startswith("ppt/theme/theme1"):
                text = blob.decode("utf-8")
                for slot, value in (("dk2", "1F2A24"), ("accent1", "0B6E4F"), ("accent2", "F28C28")):
                    start = text.index(f"<a:{slot}>")
                    end = text.index(f"</a:{slot}>") + len(f"</a:{slot}>")
                    text = text[:start] + f'<a:{slot}><a:srgbClr val="{value}"/></a:{slot}>' + text[end:]
                text = re.sub(r'(<a:majorFont><a:latin typeface=")[^"]*', r"\g<1>Georgia", text)
                text = re.sub(r'(<a:minorFont><a:latin typeface=")[^"]*', r"\g<1>Verdana", text)
                blob = text.encode("utf-8")
            dst.writestr(item, blob)
    return out.getvalue()


def create_kit(client: TestClient) -> dict:  # type: ignore[type-arg]
    response = client.post("/api/brand-kits", data={"name": "Northwind"},
                           files={"template": ("northwind.potx", make_potx(), "application/octet-stream")})
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------- PDF unit
def test_pdf_is_vector_with_embedded_urbanist(tmp_path: Path) -> None:
    slides = samples.all_layouts()
    path = build_pdf(slides, place_deck(slides, Theme()), Theme(), tmp_path / "deck.pdf", include_notes=True)
    raw = path.read_bytes()
    assert b"Urbanist" in raw and b"/FontFile2" in raw          # TrueType font embedded
    document = pdfium.PdfDocument(str(path))
    assert len(document) == 2 * len(slides)                      # slide + notes page each
    page = document[0]
    assert round(page.get_width()) == 960 and round(page.get_height()) == 540
    assert "Q3" in document[0].get_textpage().get_text_range() or document[0].get_textpage().count_chars() > 0
    chart_index = next(i for i, s in enumerate(slides) if s.layout == "chart")
    chart_page = document[2 * chart_index]
    kinds = {obj.type for obj in chart_page.get_objects()}
    assert pdfium.raw.FPDF_PAGEOBJ_PATH in kinds                 # bars drawn as paths, not a picture
    assert pdfium.raw.FPDF_PAGEOBJ_IMAGE not in kinds
    document.close()


# ---------------------------------------------------------------- export API
def test_export_pdf_images_notes(client: TestClient) -> None:
    deck = build_deck(client)
    n = len(deck["slides"])
    pdf = client.post(f"/api/decks/{deck['id']}/export", json={"format": "pdf", "include_notes": False}).json()
    assert pdf["filename"].endswith(".pdf") and pdf["report"]["checks"][1]["label"] == "Fonts embedded"
    file = client.get(f"/api/files/{pdf['file_id']}")
    assert file.status_code == 200 and file.headers["content-type"] == "application/pdf"
    assert len(pdfium.PdfDocument(file.content)) == n

    images = client.post(f"/api/decks/{deck['id']}/export", json={"format": "images"}).json()
    archive = zipfile.ZipFile(io.BytesIO(client.get(f"/api/files/{images['file_id']}").content))
    names = archive.namelist()
    assert len(names) == n and all(name.endswith(".png") for name in names)
    assert Image.open(io.BytesIO(archive.read(names[0]))).size == (1920, 1080)

    notes = client.post(f"/api/decks/{deck['id']}/export", json={"format": "notes"}).json()
    text = client.get(f"/api/files/{notes['file_id']}").text
    assert notes["filename"].endswith(".md") and text.count("\n## ") == n
    assert deck["slides"][0]["notes"].split()[0] in text


# ---------------------------------------------------------------- brand kits
def test_brand_kit_extraction(client: TestClient) -> None:
    kit = create_kit(client)
    hexes = {p["slot"]: p["hex"] for p in kit["palette"]}
    assert hexes["accent1"] == "#0B6E4F" and hexes["accent2"] == "#F28C28"
    assert kit["fonts"] == {"heading": "Georgia", "body": "Verdana"}
    assert len(kit["logos"]) == 1 and kit["logos"][0]["width"] == 200
    assert client.get(kit["logos"][0]["url"]).status_code == 200
    assert any(layout["name"] == "Blank" for layout in kit["layouts"])
    theme = kit["theme"]
    assert theme["colors"]["accent"] == "#0B6E4F" and theme["font"] == "Verdana" and theme["logo"]
    kinds = {r["kind"] for r in kit["rules"]}
    assert {"colors", "font", "logo", "min_size"} <= kinds
    assert client.get("/api/brand-kits").json()[0]["id"] == kit["id"]


def test_rules_crud_and_classification(client: TestClient) -> None:
    kit = create_kit(client)
    kit = client.post(f"/api/brand-kits/{kit['id']}/rules", json={"text": "Body text never below 14pt"}).json()
    rule = kit["rules"][-1]
    assert rule["kind"] == "min_size" and rule["params"]["pt"] == 14 and rule["source"] == "user"
    kit = client.patch(f"/api/brand-kits/{kit['id']}/rules/{rule['id']}", json={"enabled": False}).json()
    assert kit["rules"][-1]["enabled"] is False
    kit = client.delete(f"/api/brand-kits/{kit['id']}/rules/{rule['id']}").json()
    assert all(r["id"] != rule["id"] for r in kit["rules"])
    assert client.post("/api/brand-kits", files={"template": ("x.potx", b"nope", "application/octet-stream")}
                       ).status_code == 409


def test_apply_kit_brand_match_and_template_export(client: TestClient) -> None:
    kit = create_kit(client)
    deck = build_deck(client)
    before = client.get(f"/api/decks/{deck['id']}/brand-match").json()
    assert before["score"] is None
    out = client.put(f"/api/decks/{deck['id']}/brand-kit", json={"brand_kit_id": kit["id"]}).json()
    assert out["theme"]["colors"]["accent"] == "#0B6E4F"
    render = client.get(f"/api/decks/{deck['id']}/render").json()
    assert all(any(e["id"] == "brand-logo" for e in s["elements"]) for s in render)

    match = client.get(f"/api/decks/{deck['id']}/brand-match").json()
    by_kind = {r["kind"]: r for r in match["rules"]}
    assert by_kind["logo"]["passed"] and by_kind["font"]["passed"] and by_kind["colors"]["passed"]
    assert 0 <= match["score"] <= 100

    # a rule the deck breaks lowers the score and shows up as a Critic finding
    client.post(f"/api/brand-kits/{kit['id']}/rules", json={"text": "Never use type below 30 pt"})
    worse = client.get(f"/api/decks/{deck['id']}/brand-match").json()
    assert worse["score"] < match["score"]
    client.put(f"/api/decks/{deck['id']}/brand-kit", json={"brand_kit_id": kit["id"]})
    findings = client.get(f"/api/decks/{deck['id']}/critic").json()["findings"]
    assert any(f["rule"] == "brand" for f in findings)

    exported = client.post(f"/api/decks/{deck['id']}/export", json={"format": "pptx"}).json()
    prs = Presentation(io.BytesIO(client.get(f"/api/files/{exported['file_id']}").content))
    assert len(prs.slides) == len(deck["slides"])                   # template's sample slide dropped
    assert all(len(s.placeholders) == 0 for s in prs.slides)
    master_pictures = [s for s in prs.slide_masters[0].shapes if s.shape_type == 13]
    assert master_pictures                                          # the customer's master, logo included
    assert not any(sh.name.endswith("brand-logo") for s in prs.slides for sh in s.shapes)
    assert prs.slides[0].slide_layout.name == "Blank"

    pdf = client.post(f"/api/decks/{deck['id']}/export", json={"format": "pdf"}).json()
    assert pdf["bytes"] > 0

    assert client.put(f"/api/decks/{deck['id']}/brand-kit", json={"brand_kit_id": None}).json()["brand_kit_id"] is None
    assert client.delete(f"/api/brand-kits/{kit['id']}").status_code == 204
