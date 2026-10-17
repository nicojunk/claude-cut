import Foundation
import Vision
import AppKit
// Aufruf: augen bild.png ... -> datei \t augen_oben brauen_oben pupille_y (Pixel von oben) der größten Gesichtsbox, oder "none".
// Runde 5 (17.10.2026): der Gesichtsrahmen allein rutscht nach unten, wenn eine Karte die Stirn verdeckt (385 statt 358 px im
// selben Bildausschnitt); die Augen-Landmarken bleiben auf den Augen.
for p in CommandLine.arguments.dropFirst() {
    guard let img = NSImage(contentsOfFile: p), let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { continue }
    let W = Double(cg.width), H = Double(cg.height)
    let req = VNDetectFaceLandmarksRequest()
    try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
    guard let f = (req.results ?? []).max(by: { $0.boundingBox.width < $1.boundingBox.width }), let lm = f.landmarks else { print("\(p)\tnone"); continue }
    func pkt(_ r: VNFaceLandmarkRegion2D?) -> [CGPoint] { r?.pointsInImage(imageSize: CGSize(width: W, height: H)) ?? [] }
    let augen = pkt(lm.leftEye) + pkt(lm.rightEye)
    let brauen = pkt(lm.leftEyebrow) + pkt(lm.rightEyebrow)
    let pupillen = pkt(lm.leftPupil) + pkt(lm.rightPupil)
    if augen.isEmpty { print("\(p)\tnone"); continue }
    let oben = { (ps: [CGPoint]) -> Double in H - ps.map { Double($0.y) }.max()! }   // Vision: Ursprung unten links
    let pup = pupillen.isEmpty ? oben(augen) : H - pupillen.map { Double($0.y) }.reduce(0, +) / Double(pupillen.count)
    print("\(p)\t\(String(format: "%.1f %.1f %.1f", oben(augen), brauen.isEmpty ? oben(augen) : oben(brauen), pup))")
}
