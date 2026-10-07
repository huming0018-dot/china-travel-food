import UIKit
import WebKit
import BackgroundTasks
import Security

@main
final class AppDelegate: UIResponder, UIApplicationDelegate {
    var window: UIWindow?
    let collector = CollectorViewController()
    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        window = UIWindow(frame: UIScreen.main.bounds); window?.rootViewController = collector; window?.makeKeyAndVisible()
        if #available(iOS 26.0, *) {
            BGTaskScheduler.shared.register(forTaskWithIdentifier: "org.foodresearch.crowd.collect", using: .main) { [weak self] task in
                guard let t = task as? BGContinuedProcessingTask else { task.setTaskCompleted(success: false); return }
                self?.collector.continued = t
                t.progress.totalUnitCount = 20; t.progress.completedUnitCount = 0
                t.expirationHandler = { DispatchQueue.main.async { self?.collector.suspend() } }
            }
        }
        return true
    }
    func applicationDidEnterBackground(_ application: UIApplication) { collector.backgrounded() }
    func applicationWillEnterForeground(_ application: UIApplication) { collector.foregrounded() }
    func application(_ app: UIApplication, open url: URL, options: [UIApplication.OpenURLOptionsKey: Any] = [:]) -> Bool {
        guard url.scheme == "foodcrowd", url.host == "join", let fragment = url.fragment,
              fragment.range(of: "^invite=[a-f0-9]{64}$", options: .regularExpression) != nil else { return false }
        do { try collector.write("pending_invite",String(fragment.dropFirst(7))) }
        catch { return false }
        collector.control?.evaluateJavaScript("window.dispatchEvent(new Event('crowd_invite'))")
        return true
    }
}

final class CollectorViewController: UIViewController, WKScriptMessageHandler, WKNavigationDelegate {
    func isPublicPage(_ url: URL?) -> Bool {
        guard let u = url else { return false }
        return u.scheme == "https" && ["www.xiaohongshu.com", "m.xiaohongshu.com"].contains(u.host ?? "")
            && u.user == nil && u.password == nil && (u.port == nil || u.port == 443)
    }
    var control: WKWebView!, browser: WKWebView!
    var timer: Timer?, batchTimer: Timer?
    var background: UIBackgroundTaskIdentifier = .invalid
    var running = false
    var batchBaseline = 0
    // BGContinuedProcessingTask is only available on iOS 26; store as its common base.
    var continued: BGTask?
    let identifier = "org.foodresearch.crowd.collect"
    let files = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
    var assets: URL { Bundle.main.resourceURL!.appendingPathComponent("assets") }
    override func viewDidLoad() {
        super.viewDidLoad()
        let conf = WKWebViewConfiguration(); conf.userContentController.add(self, name: "crowd")
        control = WKWebView(frame: .zero, configuration: conf); browser = WKWebView()
        control.navigationDelegate = self; browser.navigationDelegate = self
        let stack = UIStackView(arrangedSubviews: [control, browser]); stack.axis = .vertical; stack.distribution = .fillEqually; stack.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(stack)
        NSLayoutConstraint.activate([stack.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor), stack.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor), stack.leadingAnchor.constraint(equalTo: view.leadingAnchor), stack.trailingAnchor.constraint(equalTo: view.trailingAnchor)])
        control.loadFileURL(assets.appendingPathComponent("controller.html"), allowingReadAccessTo: assets)
        browser.load(URLRequest(url: URL(string: "https://www.xiaohongshu.com")!))
    }
    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let u = navigationAction.request.url else { decisionHandler(.cancel); return }
        if webView === control { decisionHandler(u.isFileURL && u.path == assets.appendingPathComponent("controller.html").path ? .allow : .cancel) }
        else { decisionHandler(isPublicPage(u) || u.absoluteString == "about:blank" ? .allow : .cancel) }
    }
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        if webView === browser && running { control.evaluateJavaScript("CrowdNative.wake()") }
    }
    func encoded(_ value: Any) throws -> String { String(data: try JSONSerialization.data(withJSONObject: value, options: [.fragmentsAllowed]), encoding: .utf8)! }
    func reply(_ id: String, _ value: Any = NSNull(), error: String? = nil) {
        let json: [String: Any] = error == nil ? ["ok": true, "data": value] : ["ok": false, "error": error!]
        if let data = try? encoded(json), let quoted = try? encoded(id) { control.evaluateJavaScript("CrowdBridgeReply(\(quoted),\(data))") }
    }
    func stateFile(_ key: String) throws -> URL {
        guard key.range(of: "^[a-zA-Z0-9:_-]{1,120}$", options: .regularExpression) != nil else { throw NSError(domain: "invalid_key", code: 1) }
        try FileManager.default.createDirectory(at: files, withIntermediateDirectories: true)
        return files.appendingPathComponent(key + ".json")
    }
    func read(_ key: String) throws -> Any {
        let data: Data?
        if ["session","install_secret","pending_invite"].contains(key) {
            var result: CFTypeRef?
            let query: [String:Any] = [kSecClass as String:kSecClassGenericPassword, kSecAttrService as String:identifier, kSecAttrAccount as String:key, kSecReturnData as String:true, kSecMatchLimit as String:kSecMatchLimitOne]
            let status = SecItemCopyMatching(query as CFDictionary, &result)
            if status != errSecSuccess && status != errSecItemNotFound { throw NSError(domain: "keychain_read", code: Int(status)) }
            data = result as? Data
        } else {
            let file = try stateFile(key)
            data = FileManager.default.fileExists(atPath:file.path) ? try Data(contentsOf:file) : nil
        }
        return try data.map { try JSONSerialization.jsonObject(with: $0, options: [.fragmentsAllowed]) } ?? NSNull()
    }
    func write(_ key: String, _ value: Any) throws {
        let data = try JSONSerialization.data(withJSONObject:value, options:[.fragmentsAllowed])
        if ["session","install_secret","pending_invite"].contains(key) {
            let query:[String:Any] = [kSecClass as String:kSecClassGenericPassword, kSecAttrService as String:identifier, kSecAttrAccount as String:key]
            var status = SecItemUpdate(query as CFDictionary, [kSecValueData:data] as CFDictionary)
            if status == errSecItemNotFound { var item=query; item[kSecValueData as String]=data; item[kSecAttrAccessible as String]=kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly; status=SecItemAdd(item as CFDictionary,nil) }
            if status != errSecSuccess { throw NSError(domain:"keychain_write",code:Int(status)) }
        } else { try data.write(to:stateFile(key),options:[.atomic,.completeFileProtectionUntilFirstUserAuthentication]) }
        if #available(iOS 26.0, *), let task = continued as? BGContinuedProcessingTask,
           let state = value as? [String:Any], let received = state["notes_in_session"] as? Int {
            task.progress.completedUnitCount = min(Int64(max(0,received-batchBaseline)), task.progress.totalUnitCount)
        }
    }
    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        // The remote WebView has no handler, and subframes cannot call it.
        guard message.webView === control, message.frameInfo.isMainFrame, control.url?.path == assets.appendingPathComponent("controller.html").path,
            let text = message.body as? String, let data=text.data(using:.utf8), let m=(try? JSONSerialization.jsonObject(with:data)) as? [String:Any],
            let id=m["id"] as? String, let method=m["method"] as? String, let p=m["params"] as? [String:Any] else { return }
        let requiredStrings: [String:[String]] = ["get":["key"], "set":["key"], "open":["url"], "probe":["action"], "export":["text"]]
        if (requiredStrings[method] ?? []).contains(where: { !(p[$0] is String) }) || (method == "schedule" && !(p["when"] is Double)) {
            reply(id,error:"invalid_params"); return
        }
        do {
            switch method {
            case "get": reply(id,try read(p["key"] as! String)); return
            case "set": try write(p["key"] as! String,p["value"] ?? NSNull())
            case "begin": batchBaseline = (p["baseline"] as? Int) ?? 0; try begin()
            case "background":
                if #available(iOS 26.0, *) { reply(id,["collect_allowed":continued != nil]); }
                else { reply(id,["collect_allowed":false]); }
                return
            case "end": end()
            case "schedule":
                timer?.invalidate()
                if running { timer=Timer.scheduledTimer(withTimeInterval:max(1,(p["when"] as! Double)/1000-Date().timeIntervalSince1970),repeats:false) { [weak self] _ in self?.control.evaluateJavaScript("CrowdNative.wake()") } }
            case "cancel": timer?.invalidate()
            case "open":
                guard let u=URL(string:p["url"] as! String),isPublicPage(u) else { throw NSError(domain:"unsupported_origin",code:1) }
                browser.load(URLRequest(url:u))
            case "probe":
                guard isPublicPage(browser.url) else { reply(id,["ready":false]); return }
                let core=try String(contentsOf:assets.appendingPathComponent("core.js"),encoding:.utf8), parser=try String(contentsOf:assets.appendingPathComponent("content.js"),encoding:.utf8)
                browser.evaluateJavaScript(core+parser+";JSON.stringify(CrowdPage.probe(\(try encoded(p["action"]!))))") { [weak self] value,error in
                    guard let raw=value as? String,let bytes=raw.data(using:.utf8),let result=try? JSONSerialization.jsonObject(with:bytes) else { self?.reply(id,error:"page_not_ready"); return }
                    self?.reply(id,result)
                }; return
            case "close": browser.loadHTMLString("",baseURL:nil)
            case "showBrowser": browser.load(URLRequest(url:URL(string:"https://www.xiaohongshu.com")!))
            case "export":
                let file=FileManager.default.temporaryDirectory.appendingPathComponent("crowd-pending-evidence.json")
                try (p["text"] as! String).write(to:file,atomically:true,encoding:.utf8)
                let share=UIActivityViewController(activityItems:[file],applicationActivities:nil); share.popoverPresentationController?.sourceView=view
                present(share,animated:true)
            default: throw NSError(domain:"unknown_method",code:1)
            }
            reply(id)
        } catch { reply(id,error:(error as NSError).domain) }
    }
    func begin() throws {
        guard UIApplication.shared.applicationState == .active else { throw NSError(domain:"start_in_foreground",code:1) }
        if #available(iOS 26.0, *) {
            let request=BGContinuedProcessingTaskRequest(identifier:identifier,title:"公开笔记采集",subtitle:"用户启动的有限批次，随时可停止")
            request.strategy = .fail
            try BGTaskScheduler.shared.submit(request)
        }
        running=true
        batchTimer?.invalidate(); batchTimer=Timer.scheduledTimer(withTimeInterval:10*60,repeats:false) { [weak self] _ in self?.suspend() }
    }
    func backgrounded() {
        if !running { return }
        if #available(iOS 26.0, *), continued != nil { return }
        background=UIApplication.shared.beginBackgroundTask(withName:"crowd-checkpoint") { [weak self] in self?.suspend() }
        // Earlier systems permit a short completion window, not unattended browsing.
        DispatchQueue.main.asyncAfter(deadline:.now()+20) { [weak self] in
            guard UIApplication.shared.applicationState != .active else { return }; self?.suspend()
        }
    }
    func foregrounded() { if background != .invalid { UIApplication.shared.endBackgroundTask(background); background = .invalid } }
    func suspend() { control.evaluateJavaScript("CrowdNative.suspend()"); end() }
    func end() {
        running=false; timer?.invalidate(); batchTimer?.invalidate()
        continued?.setTaskCompleted(success:true); continued=nil
        if #available(iOS 26.0, *) { BGTaskScheduler.shared.cancel(taskRequestWithIdentifier:identifier) }
        foregrounded()
    }
}
