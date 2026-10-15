import Foundation
import Vision
import AppKit
// Batch local Apple Vision OCR, one JSON object per image. No cloud service.
let dir=CommandLine.arguments[1]
let files=try FileManager.default.contentsOfDirectory(atPath:dir).filter{$0.hasSuffix(".png")}.sorted()
let lower=CommandLine.arguments.count>2 ? Int(CommandLine.arguments[2])! : 0
let upper=CommandLine.arguments.count>3 ? Int(CommandLine.arguments[3])! : Int.max
for file in files where (Int(file.dropLast(4)) ?? -1)>=lower && (Int(file.dropLast(4)) ?? -1)<upper {
 autoreleasepool {
  let req=VNRecognizeTextRequest();req.recognitionLevel = .accurate;req.usesLanguageCorrection=false;req.recognitionLanguages=["en-US"]
  do {
   try VNImageRequestHandler(url:URL(fileURLWithPath:dir+"/"+file)).perform([req])
   let vals=(req.results ?? []).compactMap{$0.topCandidates(1).first}.map{["text":$0.string,"confidence":$0.confidence] as [String:Any]}
   let data=try JSONSerialization.data(withJSONObject:["file":file,"results":vals],options:[.sortedKeys])
   print(String(data:data,encoding:.utf8)!)
  }catch{print("{\"file\":\"\(file)\",\"error\":\"OCR failed\"}")}
 }
}
