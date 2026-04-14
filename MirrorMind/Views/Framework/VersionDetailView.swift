import SwiftUI

/// Full view of a single framework version.
/// One-tap copy lives here, plus a link to the diff if a previous version exists.
struct VersionDetailView: View {

    let version: FrameworkVersion
    let previous: FrameworkVersion?

    @State private var showingDiff = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Header card
                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        Label(version.label, systemImage: "bookmark.fill")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(.white)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 4)
                            .background(Color.accentColor, in: Capsule())

                        Spacer()

                        Text(version.formattedDate)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }

                    Text(version.autoTitle)
                        .font(.title3.weight(.semibold))
                }
                .padding()
                .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 14))

                // Action buttons
                HStack(spacing: 12) {
                    CopyOutputButton(text: version.content)
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 12))

                    if previous != nil {
                        Button {
                            showingDiff = true
                        } label: {
                            Label("What changed", systemImage: "arrow.left.arrow.right")
                                .font(.subheadline.weight(.medium))
                        }
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 12))
                    }
                }

                // Full content
                Text(version.content)
                    .font(.body)
                    .textSelection(.enabled)   // lets user select text too if they want
                    .padding()
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 14))
            }
            .padding()
        }
        .navigationTitle(version.label)
        .navigationBarTitleDisplayMode(.inline)
        .sheet(isPresented: $showingDiff) {
            if let previous {
                DiffView(old: previous, new: version)
            }
        }
    }
}

// MARK: - Preview

#Preview {
    NavigationStack {
        VersionDetailView(
            version: FrameworkVersion(
                content: "## Framework v2\n\nCore principle: humans and AI collaborate iteratively.\n\nNew: added documentation step after each session.",
                versionNumber: 2
            ),
            previous: FrameworkVersion(
                content: "## Framework v1\n\nCore principle: humans and AI collaborate iteratively.",
                versionNumber: 1
            )
        )
    }
    .modelContainer(for: FrameworkVersion.self, inMemory: true)
}
