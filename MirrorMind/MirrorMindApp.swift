import SwiftUI
import SwiftData

@main
struct MirrorMindApp: App {

    var body: some Scene {
        WindowGroup {
            TimelineView()
        }
        .modelContainer(for: FrameworkVersion.self)
    }
}
