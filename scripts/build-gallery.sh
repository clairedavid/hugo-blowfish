#!/bin/bash
# Build the About-page gallery derivatives.
#
# Sources live in photo-sources/ and are never modified. Every derivative is
# produced here, from the source pixels, in a single pass:
#
#   source -> [ICC to sRGB] -> crop -> resize -> grade -> unsharp -> strip
#          -> lossless PNG intermediate -> one JPG encode + one WebP encode
#
# The PNG intermediate is what makes "compress once" true: the JPG and the
# WebP are both encoded from uncompressed pixels, so neither is a re-encode of
# the other. Output lands in assets/images/gallery/ and is committed, because
# Hugo cannot read HEIC and has no unsharp mask or grading of its own.
#
# Re-run after changing a crop:  bash scripts/build-gallery.sh
set -euo pipefail

cd "$(dirname "$0")/.."
SRC="photo-sources"
OUT="assets/images/gallery"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$OUT"

SRGB="/System/Library/ColorSync/Profiles/sRGB Profile.icc"

# HEIC has no browser support and Hugo cannot decode it, so it is converted
# once, here, to a lossless PNG that the rest of the pipeline treats as source.
if [ ! -f "$SRC/03_AIMS_Senegal_2024.png" ]; then
  sips -s format png "$SRC/03_AIMS_Senegal_2024.HEIC" \
       --out "$SRC/03_AIMS_Senegal_2024.png" >/dev/null
fi

# Shared light grade: a touch of saturation and a very gentle S-curve. No
# filters, no colour casts.
GRADE_BASE=(-modulate 100,104,100 -sigmoidal-contrast 2,50%)
# Gentle unsharp, scaled to the output size. Sharpening always runs last, after
# the resize, so the radius matches the pixels actually shipped.
USM_MASTER=(-unsharp 0x0.8+0.55+0.02)
USM_THUMB=(-unsharp 0x0.6+0.45+0.02)

# slug | source | needs_p3_convert | master_crop | thumb_crop | special_grade
#
# Crops are computed on the SOURCE pixels and are exact 3:2 for every thumb.
# "none" means no crop at that stage. Masters keep each photo's own aspect;
# only #8 carries a crop, because centring the bike is a fact about the photo
# rather than about the thumbnail.
PHOTOS=(
  "01-atlas-cavern|01_atlas_cavern_2012.jpg|no|none|1998x1332+1+50|none"
  "02-benin-dune-seminar|02_cipma_benin_dune_seminar_2023.jpg|no|none|1077x718+1+0|none"
  "03-aims-senegal|03_AIMS_Senegal_2024.png|yes|none|4032x2688+0+336|none"
  "04-aims-south-africa|04_aims_sa_siyakhula_2024.jpg|no|none|none|none"
  "05-triathlon-hamburg|05_triathlon_hamburg_2018.jpg|no|none|1941x1294+0+0|shade"
  "06-unicycle-muizenberg|06_unicycle_muizenberg_2023.jpg|no|none|1089x726+538+30|none"
  "07-handstand-muizenberg|07_handstand_muizenberg_2023.jpg|no|none|3402x2268+360+0|none"
  "08-lake-louise-bike|08_lake_louise_bike_2026.jpg|yes|3272x2020+320+0|3030x2020+441+0|none"
)

encode() {           # encode <png-intermediate> <out-basename>
  local png="$1" base="$2"
  # JPG fallback and WebP, each a single encode from the same lossless pixels.
  magick "$png" -quality 86 -sampling-factor 2x2,1x1,1x1 -interlace Plane \
         -strip "$OUT/$base.jpg"
  cwebp -quiet -q 82 -m 6 -metadata none "$png" -o "$OUT/$base.webp"
}

render() {           # render <src> <p3> <crop> <resize-args...> <kind> <grade>
  local src="$1" p3="$2" crop="$3" kind="$4" special="$5"
  shift 5
  local args=()
  # Display P3 sources must be converted, not just stripped: dropping the ICC
  # without transforming would leave browsers reading P3 numbers as sRGB.
  [ "$p3" = "yes" ] && args+=(-profile "$SRGB")
  [ "$crop" != "none" ] && args+=(-crop "$crop" +repage)
  args+=("$@")

  local grade=("${GRADE_BASE[@]}")
  if [ "$special" = "shade" ]; then
    # #5 Hamburg: dappled shade. Lift the midtones and pull contrast back a
    # little so the light reads evenly, instead of a harder global curve.
    grade=(-gamma 1.10 -brightness-contrast 0x-6 -modulate 100,103,100
           -sigmoidal-contrast 1,50%)
  fi

  local usm=("${USM_MASTER[@]}")
  [ "$kind" = "thumb" ] && usm=("${USM_THUMB[@]}")

  magick "$SRC/$src" "${args[@]}" "${grade[@]}" "${usm[@]}" \
         -colorspace sRGB -strip "$TMP/$kind.png"
}

printf "%-24s %-14s %-14s %9s %9s\n" PHOTO MASTER THUMB WEBP JPG
for row in "${PHOTOS[@]}"; do
  IFS='|' read -r slug src p3 mcrop tcrop special <<< "$row"

  # Display master: the photo's own aspect, long edge capped at 2000. The '>'
  # flag is what guarantees no upscaling, so #2 (1080x719) stays native.
  render "$src" "$p3" "$mcrop" master "$special" -resize '2000x2000>'
  encode "$TMP/master.png" "$slug-master"

  # 3:2 thumbnail. The crop is already exact 3:2; '^' plus -extent absorbs any
  # half-pixel rounding so every thumbnail is exactly 900x600 and the grid
  # stays uniform.
  render "$src" "$p3" "$tcrop" thumb "$special" \
         -resize '900x600^' -gravity center -extent 900x600
  encode "$TMP/thumb.png" "$slug-thumb"

  printf "%-24s %-14s %-14s %9s %9s\n" "$slug" \
    "$(identify -format '%wx%h' "$OUT/$slug-master.jpg")" \
    "$(identify -format '%wx%h' "$OUT/$slug-thumb.jpg")" \
    "$(du -h "$OUT/$slug-master.webp" | cut -f1)" \
    "$(du -h "$OUT/$slug-master.jpg" | cut -f1)"
done

echo
echo "Wrote $(ls "$OUT" | wc -l | tr -d ' ') files to $OUT"
