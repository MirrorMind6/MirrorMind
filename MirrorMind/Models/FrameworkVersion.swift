import Foundation
import SwiftData

/// A single saved snapshot of the evolving framework/methodology.
/// Every time you paste a new summary from Claude, a new FrameworkVersion is created.
/// Nothing is ever deleted — the full history is always there.
@Model
final class FrameworkVersion {

    var id: UUID
    var content: String
    var timestamp: Date
    var versionNumber: Int

    /// First meaningful line of the content — used as the row title in the timeline.
    var autoTitle: String

    init(content: String, versionNumber: Int) {
        self.id = UUID()
        self.content = content
        self.timestamp = .now
        self.versionNumber = versionNumber
        self.autoTitle = Self.extractTitle(from: content)
    }

    // MARK: - Helpers

    private static func extractTitle(from content: String) -> String {
        content
            .components(separatedBy: .newlines)
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .first(where: { !$0.isEmpty })
            ?? "Untitled"
    }

    var formattedDate: String {
        timestamp.formatted(date: .abbreviated, time: .shortened)
    }

    var label: String { "v\(versionNumber)" }
}
