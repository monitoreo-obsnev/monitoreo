import Foundation
import Security

/// HTTP and the OAuth flow of a Google service account (JWT bearer, RFC 7523): the same as Net.java of the APK.
enum Net {
    static let scopes = "https://www.googleapis.com/auth/earthengine https://www.googleapis.com/auth/cloud-platform"
    static let tokenURI = "https://oauth2.googleapis.com/token"

    struct Failure: LocalizedError {
        let message: String
        var errorDescription: String? { message }
    }

    /// (status, body) of a request (BODY nil: no body), with extra HEADERS and a timeout of TIMEOUT seconds.
    static func request(method: String, url: String, body: String?, contentType: String,
                        headers: [(String, String)] = [], timeout: TimeInterval = 60) throws -> (status: Int, body: String) {
        guard let u = URL(string: url), u.scheme?.lowercased() == "https" else { throw Failure(message: "dirección no válida: \(url)") }
        var r = URLRequest(url: u, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: timeout)
        r.httpMethod = method
        r.setValue("monitoreo-campo", forHTTPHeaderField: "User-Agent")
        r.setValue("application/json", forHTTPHeaderField: "Accept")
        for (k, v) in headers { r.setValue(v, forHTTPHeaderField: k) }
        if let body = body {
            r.httpBody = Data(body.utf8)
            r.setValue(contentType, forHTTPHeaderField: "Content-Type")
        }
        let done = DispatchSemaphore(value: 0)
        var status = 0
        var text = ""
        var failure: Error?
        URLSession.shared.dataTask(with: r) { data, response, error in
            if let error = error {
                failure = error
            } else {
                status = (response as? HTTPURLResponse)?.statusCode ?? 0
                text = String(decoding: data ?? Data(), as: UTF8.self)
            }
            done.signal()
        }.resume()
        done.wait()
        if let failure = failure { throw failure }
        return (status, text)
    }

    static func b64url(_ d: Data) -> String {
        d.base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }

    /// The RSA key of a PEM "PRIVATE KEY" (PKCS#8, as in the JSON of Google Cloud) or "RSA PRIVATE KEY" (PKCS#1).
    static func privateKey(_ pem: String) throws -> SecKey {
        let b64 = pem.components(separatedBy: .newlines).filter { !$0.hasPrefix("-----") }.joined()
            .components(separatedBy: .whitespaces).joined()
        guard let der = Data(base64Encoded: b64) else { throw Failure(message: "la clave privada no es base64") }
        let pkcs1 = (try? unwrapPKCS8(der)) ?? der
        let attributes: [String: Any] = [kSecAttrKeyType as String: kSecAttrKeyTypeRSA,
                                         kSecAttrKeyClass as String: kSecAttrKeyClassPrivate]
        var error: Unmanaged<CFError>?
        guard let key = SecKeyCreateWithData(pkcs1 as CFData, attributes as CFDictionary, &error) else {
            throw Failure(message: "clave privada no válida")
        }
        return key
    }

    /// The RSAPrivateKey inside a PrivateKeyInfo ::= SEQUENCE { INTEGER version, SEQUENCE algorithm, OCTET STRING key }.
    static func unwrapPKCS8(_ der: Data) throws -> Data {
        let b = [UInt8](der)
        let bad = Failure(message: "no es PKCS#8")
        var i = 0
        func header(_ tag: UInt8) throws -> Int {
            guard i + 1 < b.count, b[i] == tag else { throw bad }
            i += 1
            var length = Int(b[i])
            i += 1
            if length & 0x80 != 0 {
                let n = length & 0x7f
                guard n > 0, n <= 4, i + n <= b.count else { throw bad }
                length = 0
                for _ in 0..<n { length = (length << 8) | Int(b[i]); i += 1 }
            }
            guard i + length <= b.count else { throw bad }
            return length
        }
        _ = try header(0x30)
        i += try header(0x02)
        i += try header(0x30)
        let n = try header(0x04)
        return Data(b[i..<(i + n)])
    }

    static func json(_ o: [String: Any]) -> String { encode(o) }

    static func encode(_ o: Any) -> String {
        guard let d = try? JSONSerialization.data(withJSONObject: o) else { return "{}" }
        return String(decoding: d, as: UTF8.self)
    }

    /// The signed JWT that asks TOKEN_URI for a token of EMAIL with the scopes for one hour.
    static func assertion(email: String, pem: String, tokenURI: String) throws -> String {
        let now = Int(Date().timeIntervalSince1970)
        let header = b64url(Data(#"{"alg":"RS256","typ":"JWT"}"#.utf8))
        let claims = json(["iss": email, "scope": scopes, "aud": tokenURI, "iat": now - 30, "exp": now + 3570])
        let unsigned = header + "." + b64url(Data(claims.utf8))
        var error: Unmanaged<CFError>?
        guard let signature = SecKeyCreateSignature(try privateKey(pem), .rsaSignatureMessagePKCS1v15SHA256,
                                                    Data(unsigned.utf8) as CFData, &error) as Data? else {
            throw Failure(message: "no se pudo firmar con la clave de la cuenta de servicio")
        }
        return unsigned + "." + b64url(signature)
    }

    /// The answer of TOKEN_URI ({"access_token", "expires_in", "token_type"}) for the service account EMAIL.
    static func serviceAccountToken(email: String, pem: String, tokenURI: String?) throws -> String {
        let uri = (tokenURI?.isEmpty ?? true) ? Net.tokenURI : tokenURI!
        // the JWT is base64url and dots: nothing to encode
        let jwt = try assertion(email: email, pem: pem, tokenURI: uri)
        let body = "grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&assertion=" + jwt
        let r = try request(method: "POST", url: uri, body: body, contentType: "application/x-www-form-urlencoded")
        if r.status != 200 { throw Failure(message: "token \(r.status): \(r.body)") }
        return r.body
    }
}

/// The secrets of the app (the JSON of the service account, the API keys): in the keychain of the iPhone, only for this
/// device; if the keychain refuses them (an app signed without its entitlement), in a protected file of the app.
enum Secrets {
    static let service = "es.ugr.monitoreo.campo"

    static func file(_ name: String) -> URL {
        let dir = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("secrets", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir.appendingPathComponent(name)
    }

    static func query(_ name: String) -> [String: Any] {
        [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
         kSecAttrAccount as String: name]
    }

    static func get(_ name: String) -> String? {
        var q = query(name)
        q[kSecReturnData as String] = true
        q[kSecMatchLimit as String] = kSecMatchLimitOne
        var out: CFTypeRef?
        if SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess, let d = out as? Data {
            return String(decoding: d, as: UTF8.self)
        }
        if let d = try? Data(contentsOf: file(name)) { return String(decoding: d, as: UTF8.self) }
        return nil
    }

    static func set(_ name: String, _ value: String) {
        delete(name)
        var q = query(name)
        q[kSecValueData as String] = Data(value.utf8)
        q[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        if SecItemAdd(q as CFDictionary, nil) != errSecSuccess {
            try? Data(value.utf8).write(to: file(name), options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        }
    }

    static func delete(_ name: String) {
        SecItemDelete(query(name) as CFDictionary)
        try? FileManager.default.removeItem(at: file(name))
    }
}
