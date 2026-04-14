import SwiftUI
import SwiftData

/// The home screen of MirrorMind.
/// Shows every saved framework version newest-first, with a badge
/// showing what changed since the previous version.
struct TimelineView: View {

    @Query(sort: \FrameworkVersion.versionNumber, order: .reverse)
    private var versions: [FrameworkVersion]

    @Environment(\.modelContext) private var modelContext
    @State private var showingPaste = false

    var body: some View {
        NavigationStack {
            Group {
                if versions.isEmpty {
                    emptyState
                } else {
                    versionList
                }
            }
            .navigationTitle("MirrorMind")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        showingPaste = true
                    } label: {
                        Image(systemName: "plus.circle.fill")
                            .font(.title3)
                    }
                    .accessibilityLabel("Paste new framework version")
                }
            }
            .sheet(isPresented: $showingPaste) {
                PasteView(nextVersionNumber: (versions.first?.versionNumber ?? 0) + 1)
            }
        }
    }

    // MARK: - Sub-views

    private var versionList: some View {
        List {
            ForEach(versions) { version in
                NavigationLink {
                    VersionDetailView(version: version, previous: previousVersion(of: version))
                } label: {
                    VersionRow(version: version, previous: previousVersion(of: version))
                }
            }
        }
        .listStyle(.insetGrouped)
    }

    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "doc.text.magnifyingglass")
                .font(.system(size: 56))
                .foregroundStyle(.secondary)

            Text("No framework versions yet")
                .font(.title3.weight(.semibold))

            Text("Paste a summary from your Claude conversation\nto start tracking your methodology.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            Button("Paste first version") {
                showingPaste = true
            }
            .buttonStyle(.borderedProminent)
            .padding(.top, 8)
        }
        .padding()
    }

    // MARK: - Helpers

    private func previousVersion(of version: FrameworkVersion) -> FrameworkVersion? {
        versions.first(where: { $0.versionNumber == version.versionNumber - 1 })
    }
}

// MARK: - VersionRow

private struct VersionRow: View {
    let version: FrameworkVersion
    let previous: FrameworkVersion?

    private var changeStats: String {
        guard let previous else { return "Initial version" }
        return DiffEngine.stats(old: previous.content, new: version.content)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(version.label)
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 7)
                    .padding(.vertical, 3)
                    .background(Color.accentColor, in: Capsule())

                Text(version.autoTitle)
                    .font(.subheadline.weight(.medium))
                    .lineLimit(1)
            }

            HStack {
                Text(version.formattedDate)
                Text("·")
                Text(changeStats)
            }
            .font(.caption)
            .foregroundStyle(.secondary)
        }
        .padding(.vertical, 4)
    }
}

// MARK: - Preview

#Preview {
    TimelineView()
        .modelContainer(for: FrameworkVersion.self, inMemory: true)
}
