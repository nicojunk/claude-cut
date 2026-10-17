import Foundation
import Vision
import AppKit
// Aufruf: swift ocr.swift bild1.png [bild2.png ...] -> je Zeile: datei \t text \t x y w h (normiert, Ursprung unten links) \t konfidenz
for p in CommandLine.arguments.dropFirst() {
    guard let img = NSImage(contentsOfFile: p), let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { continue }
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.recognitionLanguages = ["de-DE"]
    req.usesLanguageCorrection = false
    let h = VNImageRequestHandler(cgImage: cg, options: [:])
    try? h.perform([req])
    for o in (req.results ?? []) {
        guard let c = o.topCandidates(1).first else { continue }
        let b = o.boundingBox
        print("\(p)\t\(c.string)\t\(String(format: "%.4f %.4f %.4f %.4f", b.origin.x, b.origin.y, b.size.width, b.size.height))\t\(String(format: "%.2f", c.confidence))")
    }
}
