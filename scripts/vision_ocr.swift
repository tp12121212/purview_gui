import Foundation
import Vision
import ImageIO
import CoreGraphics

func loadImage(url: URL) -> CGImage? {
    guard let src = CGImageSourceCreateWithURL(url as CFURL, nil) else {
        return nil
    }
    return CGImageSourceCreateImageAtIndex(src, 0, nil)
}

func recognizeText(_ cgImage: CGImage) throws -> String {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    request.recognitionLanguages = ["en-US"]

    let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
    try handler.perform([request])

    guard let results = request.results as? [VNRecognizedTextObservation] else {
        return ""
    }

    let lines = results.compactMap { observation in
        observation.topCandidates(1).first?.string
    }
    return lines.joined(separator: "\n")
}

let args = CommandLine.arguments.dropFirst()
if args.isEmpty {
    fputs("Usage: vision_ocr <image_path> [image_path...]\n", stderr)
    exit(1)
}

for (idx, arg) in args.enumerated() {
    let url = URL(fileURLWithPath: arg)
    guard let image = loadImage(url: url) else {
        fputs("ERROR: Unable to load image at \(arg)\n", stderr)
        exit(2)
    }
    do {
        let text = try recognizeText(image)
        print(text)
    } catch {
        fputs("ERROR: Vision OCR failed for \(arg): \(error)\n", stderr)
        exit(3)
    }
    if idx < args.count - 1 {
        print("")
    }
}
