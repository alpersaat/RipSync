# Graph Report - RipSync  (2026-10-15)

## Corpus Check
- Corpus is ~33,450 words - fits in a single context window. You may not need a graph.

## Summary
- 713 nodes · 1642 edges · 35 communities (12 shown, 23 thin omitted)
- Extraction: 89% EXTRACTED · 11% INFERRED · 0% AMBIGUOUS · INFERRED: 173 edges (avg confidence: 0.88)
- Token cost: 12,500 input · 3,200 output

## Community Hubs (Navigation)
- Segmented Download Engine & Chunks
- Smart Categories & File Routing
- Database Storage & History
- Media Sniffer & Stream Extraction
- Executable Packaging & Inno Installer
- Download Table & UI Rows
- Download Scheduler Core
- YouTube Playlist Parser & Dialog
- Main Window Application Logic
- Browser Extension UI & Server
- Extension Content Script & Sniffer
- Scheduler Dialog UI
- Extension Manifest Configuration
- Extension Installation Guide UI
- Power Countdown & Sleep Manager
- Clipboard Notification Popup UI
- Add Download Dialog UI
- Queue Completion & Power Action
- HTTP Bridge Server Handler
- System Tray Integration
- Mock Range Server Handler
- CI/CD & Developer Setup
- Bug Report Template
- Feature Request Template
- Runtime Dependencies Spec

## God Nodes (most connected - your core abstractions)
1. `MainWindow` - 89 edges
2. `QueueManager` - 53 edges
3. `Database` - 48 edges
4. `DownloadScheduler` - 35 edges
5. `SchedulerDialog` - 28 edges
6. `MultiThreadDownloader` - 27 edges
7. `StreamDownloader` - 23 edges
8. `PlaylistDownloadDialog` - 23 edges
9. `SpeedLimiter` - 20 edges
10. `AddDownloadDialog` - 19 edges

## Surprising Connections (you probably didn't know these)
- `Smart Category Routing Spec` --conceptually_related_to--> `detect_category()`  [INFERRED]
  README.md → core/categories.py
- `Multi-Segmented Engine Spec (Range Requests)` --conceptually_related_to--> `MultiThreadDownloader`  [INFERRED]
  README.md → core/downloader.py
- `Download Scheduler & Power Management Spec` --conceptually_related_to--> `DownloadScheduler`  [INFERRED]
  README.md → core/scheduler.py
- `Social Media Resolver Spec (TikTok & Reels)` --conceptually_related_to--> `SocialResolver`  [INFERRED]
  README.md → core/social_resolver.py
- `Token Bucket Speed Limiter Spec` --conceptually_related_to--> `SpeedLimiter`  [INFERRED]
  README.md → core/speed_limiter.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Packaging, Installer and CI/CD Release Flow** — contributing_build_process, github_workflows_release_pipeline, build_exe_main [INFERRED 0.85]

## Communities (35 total, 23 thin omitted)

### Community 0 - "Segmented Download Engine & Chunks"
Cohesion: 0.05
Nodes (24): MultiThreadDownloader, Segment, SpeedLimiter, Multi-Segmented Engine Spec (Range Requests), Token Bucket Speed Limiter Spec, check(), main(), ServerHandler (+16 more)

### Community 1 - "Smart Categories & File Routing"
Cohesion: 0.07
Nodes (15): detect_category(), get_categorized_save_dir(), get_category_folder(), notify_download_completed(), fetch_playlist_metadata(), is_youtube_playlist_url(), normalize_playlist_url(), abort_shutdown() (+7 more)

### Community 2 - "Database Storage & History"
Cohesion: 0.06
Nodes (7): Database, QueueManager, TestSchedulerAndQueueUI, TestSequentialQueueManager, mock_start(), test_ui_integration(), TestTrayAndNotifications

### Community 3 - "Media Sniffer & Stream Extraction"
Cohesion: 0.06
Nodes (13): MediaSniffer, is_instagram_url(), is_tiktok_url(), sanitize_title(), SocialResolver, is_stream_url(), sanitize_filename(), StreamDownloader (+5 more)

### Community 4 - "Executable Packaging & Inno Installer"
Cohesion: 0.08
Nodes (19): build_inno_installer(), build_pyinstaller(), create_portable_zip(), ensure_assets(), find_iscc(), main(), Inno Setup & Executable Build Flow, _worker() (+11 more)

### Community 5 - "Download Table & UI Rows"
Cohesion: 0.09
Nodes (6): ProgressDialog, SegmentVisualizerWidget, format_eta(), format_progress_size(), format_size(), format_speed()

### Community 6 - "Download Scheduler Core"
Cohesion: 0.13
Nodes (4): DownloadScheduler, parse_time_str(), Download Scheduler & Power Management Spec, TestSchedulerLogic

### Community 7 - "YouTube Playlist Parser & Dialog"
Cohesion: 0.09
Nodes (4): YouTube Playlist Downloader Spec, PlaylistDownloadDialog, PlaylistScanThread, ThumbnailLoaderThread

### Community 9 - "Browser Extension UI & Server"
Cohesion: 0.12
Nodes (10): Extension Icon 128px, Extension Icon 16px, Extension Icon 48px, Extension Popup Interface, main(), Browser Integration & Video Sniffer Spec, RipSync Overview & IDM Architecture, RipSync Brand Logo & Application Icon (+2 more)

### Community 10 - "Extension Content Script & Sniffer"
Cohesion: 0.20
Nodes (22): attachSnifferButton(), computePosition(), createButton(), setStatus(), triggerDownload(), findInstagramMediaUrl(), findRecentMediaFromPerformance(), findTikTokVideoUrl() (+14 more)

### Community 12 - "Extension Manifest Configuration"
Cohesion: 0.10
Nodes (20): action, default_icon, default_popup, default_title, background, service_worker, content_scripts, 128 (+12 more)

### Community 25 - "CI/CD & Developer Setup"
Cohesion: 0.67
Nodes (3): Developer Guide & Environment Setup, GitHub Actions CI Test Pipeline, Development Dependencies Manifest

## Knowledge Gaps
- **17 isolated node(s):** `Social Media Resolver Spec (TikTok & Reels)`, `YouTube Playlist Downloader Spec`, `Multi-Segmented Engine Spec (Range Requests)`, `Token Bucket Speed Limiter Spec`, `Download Scheduler & Power Management Spec` (+12 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 243 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **23 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `MainWindow` connect `Main Window Application Logic` to `Segmented Download Engine & Chunks`, `Smart Categories & File Routing`, `Database Storage & History`, `Download Table & UI Rows`, `Download Scheduler Core`, `YouTube Playlist Parser & Dialog`, `Browser Extension UI & Server`, `Scheduler Dialog UI`, `Extension Installation Guide UI`, `Power Countdown & Sleep Manager`, `Clipboard Notification Popup UI`, `Add Download Dialog UI`, `Queue Completion & Power Action`, `Table Selection & Delete Actions`, `UI Initialization & Limiter Controls`, `System Tray Integration`, `Scheduler Toolbar Synchronization`, `Power Countdown Trigger Test`?**
  _High betweenness centrality (0.241) - this node is a cross-community bridge._
- **Are the 16 inferred relationships involving `MainWindow` (e.g. with `TestSchedulerAndQueueUI` and `TestTrayAndNotifications`) actually correct?**
  _`MainWindow` has 16 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Social Media Resolver Spec (TikTok & Reels)`, `YouTube Playlist Downloader Spec`, `Multi-Segmented Engine Spec (Range Requests)` to the rest of the system?**
  _17 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Segmented Download Engine & Chunks` be split into smaller, more focused modules?**
  _Cohesion score 0.0519219736087206 - nodes in this community are weakly interconnected._
- **Why does `QueueManager` connect `Database Storage & History` to `Segmented Download Engine & Chunks`, `Smart Categories & File Routing`, `Media Sniffer & Stream Extraction`, `Download Scheduler Core`, `Main Window Application Logic`, `Browser Extension UI & Server`, `Scheduler Dialog UI`, `UI Initialization & Limiter Controls`?**
  _High betweenness centrality (0.123) - this node is a cross-community bridge._
- **Are the 10 inferred relationships involving `QueueManager` (e.g. with `Database` and `MultiThreadDownloader`) actually correct?**
  _`QueueManager` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Should `Smart Categories & File Routing` be split into smaller, more focused modules?**
  _Cohesion score 0.0727927927927928 - nodes in this community are weakly interconnected._