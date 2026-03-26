# SnapFit 🔧

**Generate custom-fit 3D-printable tool holders in seconds — no CAD skills needed.**

SnapFit lets you select your power tools by brand and model (or scan them with your phone camera) and automatically generates a ready-to-print STL file. Each holder is designed to snap onto a magnetic steel wall panel system, keeping your workspace organized and every tool exactly where you left it.

---

## Features

- 🛠️ **Tool database** — pre-built profiles for DeWalt 20V, Milwaukee M18, and Ryobi ONE+ tools
- 📐 **Parametric STL generation** — custom cradle + retention lip + magnet mounting slots (20×6mm neodymium disc magnets)
- 📷 **Camera scanning** — hold your tool up to the camera and let SnapFit extract its dimensions automatically
- 💾 **Instant download** — STL files ready for BambuStudio, PrusaSlicer, or any slicer
- 🧩 **Magnetic mounting system** — holders snap onto standard steel wall panels (no drilling required)

---

## How It Works

1. Select your tool brand and model from the dropdown — or use the camera scanner
2. SnapFit generates a parametric STL holder fitted to your exact tool dimensions
3. Download and slice in BambuStudio or your preferred slicer
4. Print, insert magnets, snap onto your steel wall panel

---

## Getting Started

### Requirements
- Python 3.10+
- [CadQuery](https://cadquery.readthedocs.io/) (`pip install cadquery`)
- OpenCV (`pip install opencv-python`)
- Flask (`pip install flask`)

### Run locally
```bash
git clone https://github.com/joncorral-Hills/snapfit.git
cd snapfit
pip install -r requirements.txt
python app.py
Open http://localhost:5000 in your browser.

───

Wall Panel System

SnapFit holders are designed for use with thin steel wall panels mounted with industrial adhesive (3M VHB or similar). No drilling required — the panels stick to any smooth wall surface and the holders snap on and off magnetically.

Recommended magnets: 20×6mm neodymium disc magnets (N52), 2 per holder.

───

Roadmap

• [ ] Expanded tool database (50+ tools across 5+ brands)
• [ ] Improved camera scanning (upgrading to AI-based segmentation)
• [ ] BambuStudio / MakerWorld direct print integration
• [ ] Community tool library (user-submitted profiles)
- [ ] Mobile-optimized camera scanning

---

## Contributing

Have a tool that isn't in the database? Open an issue with the brand, model, and approximate dimensions (width × height × depth in mm) and we'll add it.

Pull requests welcome.

---

## License

MIT License — free to use, modify, and distribute.

---

*Built with Python, CadQuery, Flask, and OpenCV.*
