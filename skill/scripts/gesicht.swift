import Foundation
import Vision
import AppKit
// Aufruf: gesicht bild.png ... -> datei \t x y w h (normiert, Ursprung unten links) der größten Gesichtsbox
for p in CommandLine.arguments.dropFirst() {
    guard let img = NSImage(contentsOfFile: p), let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { continue }
    let req = VNDetectFaceRectanglesRequest()
    try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
    if let f = (req.results ?? []).max(by: { $0.boundingBox.width < $1.boundingBox.width }) {
        let b = f.boundingBox
        print("\(p)\t\(String(format: "%.4f %.4f %.4f %.4f", b.origin.x, b.origin.y, b.size.width, b.size.height))")
    } else { print("\(p)\tnone") }
}
