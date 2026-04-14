import SwiftUI
import UIKit

/// A button that copies `text` to the iOS clipboard on tap and briefly
/// shows a "Copied!" confirmation so the user knows it worked.
///
/// Usage:
///   CopyOutputButton(text: viewModel.latestCloudOutput)
///
struct CopyOutputButton: View {

    let text: String?

    @State private var didCopy = false

    var body: some View {
        Button(action: copyToClipboard) {
            Label(
                didCopy ? "Copied!" : "Copy output",
                systemImage: didCopy ? "checkmark" : "doc.on.doc"
            )
            .font(.subheadline.weight(.medium))
            .foregroundStyle(didCopy ? .green : .accentColor)
            .animation(.easeInOut(duration: 0.2), value: didCopy)
        }
        .disabled(text == nil)
        .accessibilityLabel(didCopy ? "Output copied to clipboard" : "Copy latest output to clipboard")
    }

    // MARK: - Private

    private func copyToClipboard() {
        guard let text else { return }

        UIPasteboard.general.string = text

        didCopy = true

        // Reset label after 2 seconds
        Task {
            try? await Task.sleep(for: .seconds(2))
            didCopy = false
        }
    }
}

// MARK: - Preview

#Preview("Has output") {
    CopyOutputButton(text: "Hello! I'm your AI assistant.")
        .padding()
}

#Preview("No output yet") {
    CopyOutputButton(text: nil)
        .padding()
}
