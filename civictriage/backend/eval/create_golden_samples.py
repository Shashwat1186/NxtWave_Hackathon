"""
Generate realistic sample test images with EXIF GPS metadata for golden eval/demo inputs.
"""
from pathlib import Path
from PIL import Image, ImageDraw
import piexif

OUTPUT_DIR = Path(__file__).parent / "golden_inputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _deg_to_dms_rational(deg_float: float):
    deg = int(deg_float)
    min_float = (deg_float - deg) * 60
    minute = int(min_float)
    sec_float = (min_float - minute) * 60
    sec = int(round(sec_float * 1000))
    return ((deg, 1), (minute, 1), (sec, 1000))


def create_pothole_image():
    img = Image.new("RGB", (640, 480), color=(80, 82, 85))
    draw = ImageDraw.Draw(img)
    draw.rectangle([300, 20, 340, 100], fill=(230, 230, 230))
    draw.rectangle([300, 180, 340, 260], fill=(230, 230, 230))
    draw.rectangle([300, 340, 340, 420], fill=(230, 230, 230))
    draw.ellipse([180, 200, 460, 380], fill=(35, 36, 38), outline=(20, 20, 20), width=4)
    draw.ellipse([220, 240, 420, 340], fill=(22, 23, 25))
    draw.line([250, 220, 380, 350], fill=(10, 10, 10), width=3)
    draw.line([300, 360, 430, 280], fill=(10, 10, 10), width=2)
    draw.text((20, 20), "CIVIC HAZARD: DEEP POTHOLE / ROAD COLLAPSE", fill=(255, 200, 50))
    draw.text((20, 40), "Road: Jubilee Hills Road No. 36", fill=(200, 200, 200))

    lat_dms = _deg_to_dms_rational(17.4319)
    lng_dms = _deg_to_dms_rational(78.4087)
    gps_ifd = {
        piexif.GPSIFD.GPSLatitudeRef: "N",
        piexif.GPSIFD.GPSLatitude: lat_dms,
        piexif.GPSIFD.GPSLongitudeRef: "E",
        piexif.GPSIFD.GPSLongitude: lng_dms,
    }
    exif_bytes = piexif.dump({"0th": {}, "Exif": {}, "GPS": gps_ifd})
    img.save(OUTPUT_DIR / "pothole_main_road.jpg", "JPEG", quality=90, exif=exif_bytes)


def create_water_leak_image():
    img = Image.new("RGB", (640, 480), color=(110, 115, 120))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 640, 120], fill=(160, 160, 160))
    draw.line([0, 120, 640, 120], fill=(60, 60, 60), width=4)
    draw.ellipse([120, 160, 520, 420], fill=(50, 130, 190), outline=(30, 90, 150), width=3)
    draw.ellipse([200, 210, 440, 370], fill=(70, 160, 225))
    draw.ellipse([280, 260, 360, 320], fill=(210, 240, 255))
    draw.text((20, 20), "CIVIC HAZARD: WATER PIPELINE BURST / FLOODING", fill=(255, 230, 50))
    draw.text((20, 40), "Location: Banjara Hills Road No. 12", fill=(40, 40, 40))

    lat_dms = _deg_to_dms_rational(17.4156)
    lng_dms = _deg_to_dms_rational(78.4350)
    gps_ifd = {
        piexif.GPSIFD.GPSLatitudeRef: "N",
        piexif.GPSIFD.GPSLatitude: lat_dms,
        piexif.GPSIFD.GPSLongitudeRef: "E",
        piexif.GPSIFD.GPSLongitude: lng_dms,
    }
    exif_bytes = piexif.dump({"0th": {}, "Exif": {}, "GPS": gps_ifd})
    img.save(OUTPUT_DIR / "water_leak_main.jpg", "JPEG", quality=90, exif=exif_bytes)


def create_streetlight_image():
    img = Image.new("RGB", (640, 480), color=(20, 22, 30))
    draw = ImageDraw.Draw(img)
    draw.polygon([(0, 480), (220, 250), (420, 250), (640, 480)], fill=(40, 42, 48))
    draw.line([480, 450, 460, 150], fill=(120, 125, 130), width=8)
    draw.line([460, 150, 390, 130], fill=(120, 125, 130), width=6)
    draw.ellipse([370, 130, 400, 160], fill=(70, 70, 70), outline=(200, 50, 50), width=2)
    draw.line([385, 160, 395, 190], fill=(220, 50, 50), width=2)
    draw.line([380, 160, 375, 185], fill=(50, 120, 220), width=2)
    draw.text((20, 20), "CIVIC HAZARD: BROKEN STREETLIGHT & EXPOSED WIRES", fill=(255, 100, 100))
    draw.text((20, 40), "Location: Madhapur Main Road near Hitec City", fill=(180, 180, 180))

    lat_dms = _deg_to_dms_rational(17.4485)
    lng_dms = _deg_to_dms_rational(78.3908)
    gps_ifd = {
        piexif.GPSIFD.GPSLatitudeRef: "N",
        piexif.GPSIFD.GPSLatitude: lat_dms,
        piexif.GPSIFD.GPSLongitudeRef: "E",
        piexif.GPSIFD.GPSLongitude: lng_dms,
    }
    exif_bytes = piexif.dump({"0th": {}, "Exif": {}, "GPS": gps_ifd})
    img.save(OUTPUT_DIR / "streetlight_broken.jpg", "JPEG", quality=90, exif=exif_bytes)


def create_garbage_image():
    img = Image.new("RGB", (640, 480), color=(90, 85, 75))
    draw = ImageDraw.Draw(img)
    draw.polygon([(150, 450), (320, 180), (520, 450)], fill=(70, 60, 50))
    # Plastic & waste patches
    draw.ellipse([220, 320, 310, 400], fill=(30, 120, 60)) # green bag
    draw.ellipse([320, 340, 420, 410], fill=(40, 90, 180)) # blue plastic
    draw.ellipse([270, 240, 360, 300], fill=(210, 200, 50)) # yellow wrapper
    draw.text((20, 20), "CIVIC HAZARD: UNCOLLECTED GARBAGE DUMP ON PUBLIC ROAD", fill=(255, 180, 50))
    draw.text((20, 40), "Location: Charminar Old City Market", fill=(220, 220, 220))

    lat_dms = _deg_to_dms_rational(17.3616)
    lng_dms = _deg_to_dms_rational(78.4747)
    gps_ifd = {
        piexif.GPSIFD.GPSLatitudeRef: "N",
        piexif.GPSIFD.GPSLatitude: lat_dms,
        piexif.GPSIFD.GPSLongitudeRef: "E",
        piexif.GPSIFD.GPSLongitude: lng_dms,
    }
    exif_bytes = piexif.dump({"0th": {}, "Exif": {}, "GPS": gps_ifd})
    img.save(OUTPUT_DIR / "garbage_overflow.jpg", "JPEG", quality=90, exif=exif_bytes)


def create_sewage_image():
    img = Image.new("RGB", (640, 480), color=(60, 65, 60))
    draw = ImageDraw.Draw(img)
    # Manhole
    draw.ellipse([240, 180, 400, 340], fill=(30, 30, 30), outline=(100, 100, 100), width=6)
    # Dirty blackwater overflow
    draw.ellipse([160, 220, 480, 440], fill=(35, 45, 30), outline=(20, 30, 15), width=2)
    draw.text((20, 20), "CIVIC HAZARD: OPEN SEWER OVERFLOW & FOUL STENCH", fill=(100, 255, 100))
    draw.text((20, 40), "Location: Ameerpet Commercial Hub Road", fill=(200, 200, 200))

    lat_dms = _deg_to_dms_rational(17.4375)
    lng_dms = _deg_to_dms_rational(78.4483)
    gps_ifd = {
        piexif.GPSIFD.GPSLatitudeRef: "N",
        piexif.GPSIFD.GPSLatitude: lat_dms,
        piexif.GPSIFD.GPSLongitudeRef: "E",
        piexif.GPSIFD.GPSLongitude: lng_dms,
    }
    exif_bytes = piexif.dump({"0th": {}, "Exif": {}, "GPS": gps_ifd})
    img.save(OUTPUT_DIR / "sewage_overflow.jpg", "JPEG", quality=90, exif=exif_bytes)


if __name__ == "__main__":
    create_pothole_image()
    create_water_leak_image()
    create_streetlight_image()
    create_garbage_image()
    create_sewage_image()
    print("All 5 golden sample images created successfully!")
