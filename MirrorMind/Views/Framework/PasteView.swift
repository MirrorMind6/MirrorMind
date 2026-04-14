import SwiftUI
import SwiftData

/// Sheet where the user pastes a framework summary copied from Claude.
/// One tap on "Save" creates a new versioned entry.
struct PasteView: View {

    let nextVersionNumber: Int

    @Environment(\.modelContext) private var modelContext
    @Environment(\.dismiss) private var dismiss

    @State private var text = ""
    @FocusState private var editorFocused: Bool

    private var isEmpty: Bool {
        text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Hint bar
                HStack {
                    Image(systemName: "arrow.down.doc")
                    Text("Paste your Claude summary below")
                    Spacer()
                    Text("v\(nextVersionNumber)")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(Color.accentColor, in: Capsule())
                }
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .padding(.horizontal)
                .padding(.vertical, 10)
                .background(Color(.secondarySystemBackground))

                // Editor
                TextEditor(text: $text)
                    .focused($editorFocused)
                    .font(.body)
                    .padding(.horizontal, 12)
                    .padding(.top, 8)
            }
            .navigationTitle("New Version")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { save() }
                        .disabled(isEmpty)
                        .fontWeight(.semibold)
                }
            }
            .onAppear {
                // Give keyboard a moment then focus
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                    editorFocused = true
                }
            }
        }
    }

    // MARK: - Save

    private func save() {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }

        let version = FrameworkVersion(content: trimmed, versionNumber: nextVersionNumber)
        modelContext.insert(version)
        dismiss()
    }
}

// MARK: - Preview

#Preview {
    PasteView(nextVersionNumber: 3)
        .modelContainer(for: FrameworkVersion.self, inMemory: true)
}
