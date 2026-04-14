import Foundation

/// Thin wrapper around the Anthropic Messages API.
/// Replace `apiKey` with your key (preferably loaded from a secure store,
/// not hardcoded) before shipping.
final class CloudService {

    static let shared = CloudService()
    private init() {}

    private let apiKey = ProcessInfo.processInfo.environment["ANTHROPIC_API_KEY"] ?? ""
    private let model  = "claude-sonnet-4-6"
    private let url    = URL(string: "https://api.anthropic.com/v1/messages")!

    // MARK: - Public

    /// Sends the current conversation to Claude and returns the assistant reply.
    func complete(messages: [CloudOutputViewModel.Message]) async throws -> String {
        let body = RequestBody(
            model: model,
            maxTokens: 1024,
            messages: messages.map { .init(role: $0.role == .user ? "user" : "assistant",
                                           content: $0.content) }
        )

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json",  forHTTPHeaderField: "Content-Type")
        request.setValue(apiKey,              forHTTPHeaderField: "x-api-key")
        request.setValue("2023-06-01",        forHTTPHeaderField: "anthropic-version")
        request.httpBody = try JSONEncoder().encode(body)

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            let msg = String(data: data, encoding: .utf8) ?? "Unknown error"
            throw CloudError.apiError(msg)
        }

        let decoded = try JSONDecoder().decode(ResponseBody.self, from: data)
        return decoded.content.first?.text ?? ""
    }

    // MARK: - Codable types

    private struct RequestBody: Encodable {
        let model: String
        let maxTokens: Int
        let messages: [Msg]

        struct Msg: Encodable {
            let role: String
            let content: String
        }

        enum CodingKeys: String, CodingKey {
            case model, messages
            case maxTokens = "max_tokens"
        }
    }

    private struct ResponseBody: Decodable {
        let content: [ContentBlock]
        struct ContentBlock: Decodable {
            let text: String
        }
    }

    enum CloudError: LocalizedError {
        case apiError(String)
        var errorDescription: String? {
            switch self { case .apiError(let msg): "API error: \(msg)" }
        }
    }
}
