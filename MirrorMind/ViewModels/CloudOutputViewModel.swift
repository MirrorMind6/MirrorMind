import Foundation
import Combine

/// Tracks the conversation history with a cloud AI service and exposes
/// the latest assistant response for on-demand clipboard copying.
@MainActor
final class CloudOutputViewModel: ObservableObject {

    struct Message: Identifiable {
        let id = UUID()
        let role: Role
        let content: String
        let timestamp: Date

        enum Role { case user, assistant }
    }

    @Published private(set) var messages: [Message] = []
    @Published private(set) var isLoading = false
    @Published private(set) var errorMessage: String?

    /// The most recent assistant response, or nil if none exists yet.
    var latestCloudOutput: String? {
        messages.last(where: { $0.role == .assistant })?.content
    }

    // MARK: - Sending a message

    func send(_ userText: String) async {
        guard !userText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }

        messages.append(Message(role: .user, content: userText, timestamp: .now))
        isLoading = true
        errorMessage = nil

        do {
            let response = try await CloudService.shared.complete(messages: messages)
            messages.append(Message(role: .assistant, content: response, timestamp: .now))
        } catch {
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }
}
