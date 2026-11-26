import CoreLocation
import UIKit
import UniformTypeIdentifiers
import WebKit

/// MonitorEO Campo on the iPhone: the same web page as the APK (the folder www of the app), served from
/// campo://localhost, with the same bridge: window.Android.call(callbackId, method, argument), answered with
/// window.AndroidCallback(id, json). What a page cannot do well is done here: the token of the service account (its key
/// never reaches the page), any HTTP request without CORS (the broker of MonitorEO), the API keys of the assistant, the
/// location of the GPS and the files of the phone. See MainActivity.java for the same on Android.
final class WebViewController: UIViewController, WKScriptMessageHandler, WKNavigationDelegate, WKUIDelegate,
    UIDocumentPickerDelegate, CLLocationManagerDelegate {

    static let scheme = "campo"
    static let start = URL(string: "campo://localhost/index.html")!
    static let maxFile = 8 * 1024 * 1024
    static let gpsTimeout: TimeInterval = 30  // s: the best fix until then
    static let gpsGood: CLLocationAccuracy = 8  // m: a fix this precise ends the search at once
    static let aiProviders = ["claude", "gemini", "glm"]

    var web: WKWebView!
    let work = DispatchQueue(label: "es.ugr.monitoreo.campo.work", qos: .userInitiated, attributes: .concurrent)

    let tokenLock = NSLock()
    var token: String?
    var tokenExpiry = Date.distantPast

    // Page --------------------------------------------------------------------------------------------------------------

    override func loadView() {
        let configuration = WKWebViewConfiguration()
        configuration.setURLSchemeHandler(AssetHandler(), forURLScheme: Self.scheme)
        configuration.websiteDataStore = .default()
        let content = WKUserContentController()
        content.add(WeakHandler(self), name: "campo")
        content.addUserScript(WKUserScript(source: """
            window.Android = {call: function (id, method, arg) {
              window.webkit.messageHandlers.campo.postMessage({id: String(id), method: String(method), arg: arg == null ? '' : String(arg)});
            }};
            window.CampoPlatform = 'ios';
            """, injectionTime: .atDocumentStart, forMainFrameOnly: true))
        configuration.userContentController = content

        let root = UIView()
        root.backgroundColor = UIColor { t in
            t.userInterfaceStyle == .dark ? UIColor(red: 0x11 / 255.0, green: 0x16 / 255.0, blue: 0x13 / 255.0, alpha: 1)
                : UIColor(red: 0xf4 / 255.0, green: 0xf6 / 255.0, blue: 0xf3 / 255.0, alpha: 1)
        }
        web = WKWebView(frame: .zero, configuration: configuration)
        web.isOpaque = false
        web.backgroundColor = .clear
        web.navigationDelegate = self
        web.uiDelegate = self
        web.scrollView.contentInsetAdjustmentBehavior = .never
        web.scrollView.bounces = false
        web.translatesAutoresizingMaskIntoConstraints = false
        root.addSubview(web)
        let safe = root.safeAreaLayoutGuide
        NSLayoutConstraint.activate([
            web.topAnchor.constraint(equalTo: safe.topAnchor),
            web.bottomAnchor.constraint(equalTo: safe.bottomAnchor),
            web.leadingAnchor.constraint(equalTo: safe.leadingAnchor),
            web.trailingAnchor.constraint(equalTo: safe.trailingAnchor),
        ])
        view = root
        web.load(URLRequest(url: Self.start))
    }

    /// Links out of the app open in Safari.
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = action.request.url, let scheme = url.scheme?.lowercased() else { return decisionHandler(.cancel) }
        if scheme == Self.scheme || scheme == "about" || scheme == "blob" || scheme == "data" { return decisionHandler(.allow) }
        if action.targetFrame?.isMainFrame ?? true {
            if ["http", "https", "mailto", "tel"].contains(scheme) { UIApplication.shared.open(url) }
            return decisionHandler(.cancel)
        }
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = action.request.url, ["http", "https"].contains(url.scheme?.lowercased() ?? "") {
            UIApplication.shared.open(url)
        }
        return nil
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        webView.load(URLRequest(url: Self.start))
    }

    // alert, confirm and prompt of the page
    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let a = UIAlertController(title: nil, message: message, preferredStyle: .alert)
        a.addAction(UIAlertAction(title: "Aceptar", style: .default) { _ in completionHandler() })
        present(a, animated: true)
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let a = UIAlertController(title: nil, message: message, preferredStyle: .alert)
        a.addAction(UIAlertAction(title: "Cancelar", style: .cancel) { _ in completionHandler(false) })
        a.addAction(UIAlertAction(title: "Aceptar", style: .default) { _ in completionHandler(true) })
        present(a, animated: true)
    }

    func webView(_ webView: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String, defaultText: String?,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (String?) -> Void) {
        let a = UIAlertController(title: nil, message: prompt, preferredStyle: .alert)
        a.addTextField { $0.text = defaultText; $0.clearButtonMode = .whileEditing }
        a.addAction(UIAlertAction(title: "Cancelar", style: .cancel) { _ in completionHandler(nil) })
        a.addAction(UIAlertAction(title: "Aceptar", style: .default) { _ in completionHandler(a.textFields?.first?.text ?? "") })
        present(a, animated: true)
    }

    // Answers to the page -----------------------------------------------------------------------------------------------

    static func jsString(_ s: String) -> String {
        let a = Net.encode([s])  // ["…"]
        return String(a.dropFirst().dropLast())
    }

    static func error(_ message: String) -> String { Net.json(["error": message]) }

    func answer(_ id: String, _ json: String) {
        let js = "window.AndroidCallback && window.AndroidCallback(\(Self.jsString(id)),\(Self.jsString(json)))"
        DispatchQueue.main.async { self.web.evaluateJavaScript(js, completionHandler: nil) }
    }

    func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let d = message.body as? [String: Any], let id = d["id"] as? String, let method = d["method"] as? String
        else { return }
        let arg = d["arg"] as? String ?? ""
        switch method {
        case "pickServiceAccount": pick(id, serviceAccount: true)
        case "openFile": pick(id, serviceAccount: false)
        case "saveFile": save(id, arg)
        case "locate": locate(id)
        case "openUrl":
            if let u = URL(string: arg), ["http", "https", "mailto"].contains(u.scheme?.lowercased() ?? "") {
                UIApplication.shared.open(u)
            }
            answer(id, "{}")
        default:
            work.async {
                let out: String
                do { out = try self.dispatch(method, arg) } catch { out = Self.error(error.localizedDescription) }
                self.answer(id, out)
            }
        }
    }

    func object(_ arg: String) throws -> [String: Any] {
        guard let o = try JSONSerialization.jsonObject(with: Data(arg.utf8)) as? [String: Any] else {
            throw Net.Failure(message: "argumento no válido")
        }
        return o
    }

    static func text(_ v: Any?) -> String? {
        if v == nil || v is NSNull { return nil }
        if let s = v as? String { return s }
        return Net.encode(v!)
    }

    func dispatch(_ method: String, _ arg: String) throws -> String {
        switch method {
        case "serviceAccountInfo":
            return try serviceAccountInfo()
        case "serviceAccountToken":
            return try serviceAccountToken(force: arg == "1")
        case "clearServiceAccount":
            Secrets.delete("sa")
            tokenLock.lock(); token = nil; tokenLock.unlock()
            return "{}"
        case "http":
            let a = try object(arg)
            guard let url = a["url"] as? String else { throw Net.Failure(message: "falta url") }
            let r = try Net.request(method: a["method"] as? String ?? "GET", url: url, body: Self.text(a["body"]),
                                    contentType: a["contentType"] as? String ?? "application/json")
            return Net.json(["status": r.status, "body": r.body])
        case "aiKeys":
            return aiKeys()
        case "aiSetKey":
            let a = try object(arg)
            let p = try aiProvider(a["provider"] as? String ?? "")
            let k = (a["key"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            if k.count < 8 { return Self.error("la clave es demasiado corta") }
            Secrets.set("ai_key_" + p, k)
            return aiKeys()
        case "aiClearKey":
            Secrets.delete("ai_key_" + (try aiProvider(arg)))
            return aiKeys()
        case "aiRequest":
            return try aiRequest(try object(arg))
        case "appInfo":
            let info = Bundle.main.infoDictionary ?? [:]
            return Net.json(["version": info["CFBundleShortVersionString"] as? String ?? "",
                             "code": Int(info["CFBundleVersion"] as? String ?? "") ?? 0, "platform": "ios"])
        default:
            return Self.error("unknown method \(method)")
        }
    }

    // The keys of the AI providers --------------------------------------------------------------------------------------
    // Like the key of the service account, an API key stays in the keychain: the page sends the body of a request and
    // the provider, and the key is added here, to a fixed URL of that provider.

    func aiProvider(_ p: String) throws -> String {
        guard Self.aiProviders.contains(p) else { throw Net.Failure(message: "proveedor desconocido: \(p)") }
        return p
    }

    func aiKeys() -> String {
        var out: [String: String] = [:]
        for p in Self.aiProviders {
            let k = Secrets.get("ai_key_" + p)
            out[p] = k == nil ? "" : "…" + String(k!.suffix(4))
        }
        return Net.json(out)
    }

    /// A request of the assistant (ai.js) to its language model: "monitoreo", the route /chat of the broker of MonitorEO
    /// (its key is in the broker and never leaves it; only that route of an https host), or the API of Claude, Gemini
    /// (compatible with OpenAI) or GLM with the key of the user, added here to the fixed URL of that provider.
    func aiRequest(_ a: [String: Any]) throws -> String {
        let p = a["provider"] as? String ?? ""
        let url: String
        var headers: [(String, String)] = []
        if p == "monitoreo" {
            url = a["url"] as? String ?? ""
            if url.range(of: #"^https://[A-Za-z0-9.\-]+(:[0-9]+)?/chat\?user=mo-[0-9a-f]{16}$"#, options: .regularExpression) == nil {
                return Self.error("dirección del broker no válida")
            }
        } else {
            let q = try aiProvider(p)
            guard let key = Secrets.get("ai_key_" + q) else { return Self.error("no hay clave de API para \(q): ponla en Ajustes") }
            switch q {
            case "claude":
                let beta = a["beta"] as? String ?? ""
                if beta.range(of: #"^[a-z0-9\-,]{0,200}$"#, options: .regularExpression) == nil { return Self.error("beta no válida") }
                url = "https://api.anthropic.com/v1/messages"
                headers = [("x-api-key", key), ("anthropic-version", "2023-06-01")]
                if !beta.isEmpty { headers.append(("anthropic-beta", beta)) }
            case "gemini":
                url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
                headers = [("Authorization", "Bearer " + key)]
            default:
                url = "https://api.z.ai/api/paas/v4/chat/completions"
                headers = [("Authorization", "Bearer " + key), ("Accept-Language", "en-US,en")]
            }
        }
        let r = try Net.request(method: "POST", url: url, body: Self.text(a["body"]) ?? "{}", contentType: "application/json",
                                headers: headers, timeout: 300)
        return Net.json(["status": r.status, "body": r.body])
    }

    // The service account -----------------------------------------------------------------------------------------------

    func serviceAccount() throws -> [String: Any]? {
        guard let text = Secrets.get("sa") else { return nil }
        return try object(text)
    }

    func serviceAccountInfo() throws -> String {
        guard let j = try serviceAccount() else { return "{}" }
        return Net.json(["client_email": j["client_email"] as? String ?? "", "project_id": j["project_id"] as? String ?? ""])
    }

    func serviceAccountToken(force: Bool) throws -> String {
        guard let j = try serviceAccount() else { return Self.error("no hay cuenta de servicio: elige su JSON en Ajustes") }
        tokenLock.lock()
        defer { tokenLock.unlock() }
        let now = Date()
        if force || token == nil || tokenExpiry.timeIntervalSince(now) < 5 * 60 {
            let reply = try object(try Net.serviceAccountToken(email: j["client_email"] as? String ?? "",
                                                                pem: j["private_key"] as? String ?? "",
                                                                tokenURI: j["token_uri"] as? String))
            guard let t = reply["access_token"] as? String else { throw Net.Failure(message: "respuesta sin token") }
            token = t
            tokenExpiry = now.addingTimeInterval((reply["expires_in"] as? Double) ?? 3600)
        }
        return Net.json(["access_token": token!, "expires_in": Int(tokenExpiry.timeIntervalSince(now)),
                         "project": j["project_id"] as? String ?? ""])
    }

    func saveServiceAccount(_ text: String) throws -> String {
        let j = try object(text)
        guard j["type"] as? String == "service_account", let pem = j["private_key"] as? String, j["client_email"] is String else {
            return Self.error("ese archivo no es el JSON de una clave de cuenta de servicio de Google Cloud")
        }
        _ = try Net.privateKey(pem)  // a key that iOS can read
        Secrets.set("sa", text)
        tokenLock.lock(); token = nil; tokenLock.unlock()
        return try serviceAccountInfo()
    }

    // Files -------------------------------------------------------------------------------------------------------------

    var openPicker: UIDocumentPickerViewController?
    var openCb: String?
    var openIsServiceAccount = false
    var savePicker: UIDocumentPickerViewController?
    var saveCb: String?

    func pick(_ id: String, serviceAccount: Bool) {
        if let old = openCb { answer(old, #"{"cancelled":true}"#) }
        openCb = id
        openIsServiceAccount = serviceAccount
        let p = UIDocumentPickerViewController(forOpeningContentTypes: [.item], asCopy: true)
        p.delegate = self
        p.allowsMultipleSelection = false
        openPicker = p
        present(p, animated: true)
    }

    func save(_ id: String, _ arg: String) {
        do {
            let a = try object(arg)
            var name = (a["name"] as? String ?? "datos.txt").components(separatedBy: CharacterSet(charactersIn: "/\\:")).joined(separator: "_")
            if name.isEmpty { name = "datos.txt" }
            let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            let file = dir.appendingPathComponent(name)
            try Data((a["text"] as? String ?? "").utf8).write(to: file)
            if let old = saveCb { answer(old, #"{"cancelled":true}"#) }
            saveCb = id
            let p = UIDocumentPickerViewController(forExporting: [file], asCopy: true)
            p.delegate = self
            savePicker = p
            present(p, animated: true)
        } catch {
            answer(id, Self.error(error.localizedDescription))
        }
    }

    func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) {
        if controller === savePicker {
            savePicker = nil
            if let id = saveCb { saveCb = nil; answer(id, Net.json(["ok": true, "name": urls.first?.lastPathComponent ?? ""])) }
            return
        }
        openPicker = nil
        guard let id = openCb else { return }
        openCb = nil
        guard let url = urls.first else { return answer(id, #"{"cancelled":true}"#) }
        let serviceAccount = openIsServiceAccount
        work.async {
            let scoped = url.startAccessingSecurityScopedResource()
            defer { if scoped { url.stopAccessingSecurityScopedResource() } }
            do {
                let data = try Data(contentsOf: url)
                if data.count > Self.maxFile { throw Net.Failure(message: "archivo demasiado grande") }
                let text = String(decoding: data, as: UTF8.self)
                if serviceAccount {
                    self.answer(id, try self.saveServiceAccount(text))
                } else {
                    self.answer(id, Net.json(["name": url.lastPathComponent, "text": text]))
                }
            } catch {
                self.answer(id, Self.error(error.localizedDescription))
            }
        }
    }

    func documentPickerWasCancelled(_ controller: UIDocumentPickerViewController) {
        let id: String?
        if controller === savePicker { id = saveCb; saveCb = nil; savePicker = nil } else { id = openCb; openCb = nil; openPicker = nil }
        if let id = id { answer(id, #"{"cancelled":true}"#) }
    }

    // Location ----------------------------------------------------------------------------------------------------------

    let locations = CLLocationManager()
    var locateCb: String?
    var locating = false
    var best: CLLocation?
    var gpsTimer: Timer?

    func locate(_ id: String) {
        if let old = locateCb { answer(old, #"{"cancelled":true}"#) }
        locateCb = id
        locations.delegate = self
        locations.desiredAccuracy = kCLLocationAccuracyBest
        switch locations.authorizationStatus {
        case .notDetermined: locations.requestWhenInUseAuthorization()  // goes on in locationManagerDidChangeAuthorization
        case .denied, .restricted: finishLocation("sin permiso de ubicación: actívalo en Ajustes › MonitorEO Campo")
        default: startLocation()
        }
    }

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        guard locateCb != nil, !locating else { return }
        switch manager.authorizationStatus {
        case .authorizedWhenInUse, .authorizedAlways: startLocation()
        case .denied, .restricted: finishLocation("sin permiso de ubicación")
        default: break
        }
    }

    func startLocation() {
        if locating { return }
        locating = true
        best = nil
        if locations.accuracyAuthorization == .reducedAccuracy {
            locations.requestTemporaryFullAccuracyAuthorization(withPurposeKey: "campo")
        }
        locations.startUpdatingLocation()
        gpsTimer?.invalidate()
        gpsTimer = Timer.scheduledTimer(withTimeInterval: Self.gpsTimeout, repeats: false) { [weak self] _ in
            self?.finishLocation(nil)
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations fixes: [CLLocation]) {
        guard locating else { return }
        for l in fixes where l.horizontalAccuracy >= 0 && -l.timestamp.timeIntervalSinceNow < 60 {
            if best == nil || l.horizontalAccuracy <= best!.horizontalAccuracy { best = l }
            if l.horizontalAccuracy <= Self.gpsGood { return finishLocation(nil) }
        }
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        if (error as? CLError)?.code == .denied { finishLocation("sin permiso de ubicación") }
    }

    func finishLocation(_ failure: String?) {
        gpsTimer?.invalidate()
        gpsTimer = nil
        if locating { locations.stopUpdatingLocation() }
        locating = false
        guard let id = locateCb else { return }
        locateCb = nil
        var l = best
        var stale = false
        if failure == nil, l == nil, let last = locations.location {  // nothing new: the last fix known, marked as old
            l = last
            stale = true
        }
        if let failure = failure { return answer(id, Self.error(failure)) }
        guard let fix = l else { return answer(id, Self.error("no hay señal de GPS: prueba al aire libre")) }
        var altitude: Any = NSNull()
        if fix.verticalAccuracy >= 0 { altitude = fix.altitude }
        answer(id, Net.json(["lat": fix.coordinate.latitude, "lon": fix.coordinate.longitude, "accuracy": fix.horizontalAccuracy,
                             "altitude": altitude, "provider": "gps",
                             "time": Int(fix.timestamp.timeIntervalSince1970 * 1000), "stale": stale]))
    }
}

/// The page of the app, from the folder www of the bundle (the same files as app/src/main/assets/www of the APK).
final class AssetHandler: NSObject, WKURLSchemeHandler {
    let root = Bundle.main.resourceURL!.appendingPathComponent("www", isDirectory: true).standardizedFileURL

    static func mime(_ ext: String) -> String {
        switch ext.lowercased() {
        case "html": return "text/html; charset=utf-8"
        case "js": return "application/javascript; charset=utf-8"
        case "css": return "text/css; charset=utf-8"
        case "png": return "image/png"
        case "svg": return "image/svg+xml"
        case "json": return "application/json"
        default: return "application/octet-stream"
        }
    }

    func webView(_ webView: WKWebView, start task: WKURLSchemeTask) {
        guard let url = task.request.url else { return task.didFailWithError(URLError(.badURL)) }
        var path = url.path
        if path.isEmpty || path == "/" { path = "/index.html" }
        let file = root.appendingPathComponent(String(path.dropFirst())).standardizedFileURL
        if file.path.hasPrefix(root.path + "/"), let data = try? Data(contentsOf: file) {
            let headers = ["Content-Type": Self.mime(file.pathExtension), "Content-Length": String(data.count),
                           "Cache-Control": "no-cache"]
            task.didReceive(HTTPURLResponse(url: url, statusCode: 200, httpVersion: "HTTP/1.1", headerFields: headers)!)
            task.didReceive(data)
        } else {
            task.didReceive(HTTPURLResponse(url: url, statusCode: 404, httpVersion: "HTTP/1.1",
                                            headerFields: ["Content-Type": "text/plain"])!)
            task.didReceive(Data("not found".utf8))
        }
        task.didFinish()
    }

    func webView(_ webView: WKWebView, stop task: WKURLSchemeTask) {}
}

/// WKUserContentController keeps its handlers: this one does not keep the controller.
final class WeakHandler: NSObject, WKScriptMessageHandler {
    weak var target: WKScriptMessageHandler?
    init(_ target: WKScriptMessageHandler) { self.target = target }
    func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
        target?.userContentController(controller, didReceive: message)
    }
}
