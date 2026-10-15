package local.sovereigntv.control

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.AtomicFile
import java.io.ByteArrayInputStream
import java.io.File
import java.math.BigInteger
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.MessageDigest
import java.security.Principal
import java.security.PrivateKey
import java.security.SecureRandom
import java.security.cert.CertificateException
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate
import java.security.interfaces.ECPublicKey
import java.security.interfaces.RSAPublicKey
import java.security.spec.ECGenParameterSpec
import java.util.Base64
import java.util.Date
import javax.net.ssl.*
import javax.security.auth.x500.X500Principal

/** No private key export, CA service, downloaded trust or network discovery. */
object Identity {
    const val DEVICE_ALIAS = "sovereign-control-device-v1"
    @Synchronized fun ensure(alias: String = DEVICE_ALIAS): X509Certificate {
        val store = keyStore()
        if (!store.containsAlias(alias)) {
            val now = System.currentTimeMillis()
            KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore").apply {
                initialize(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY)
                    .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
                    .setDigests(KeyProperties.DIGEST_NONE, KeyProperties.DIGEST_SHA256, KeyProperties.DIGEST_SHA384, KeyProperties.DIGEST_SHA512)
                    .setCertificateSubject(X500Principal("CN=Sovereign local control"))
                    .setCertificateSerialNumber(BigInteger(128, SecureRandom()).add(BigInteger.ONE))
                    .setCertificateNotBefore(Date(now - 86400000L)).setCertificateNotAfter(Date(now + 10L * 365 * 86400000))
                    .build())
                generateKeyPair()
            }
        }
        return keyStore().getCertificate(alias) as X509Certificate
    }
    fun keyStore(): KeyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
    fun digest(bytes: ByteArray): String = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
    fun pin(certificate: X509Certificate) = digest(certificate.encoded)
    fun pem(certificate: X509Certificate) = "-----BEGIN CERTIFICATE-----\n" + Base64.getMimeEncoder(64, byteArrayOf(10)).encodeToString(certificate.encoded) + "\n-----END CERTIFICATE-----\n"
    fun certificate(input: ByteArray): X509Certificate {
        require(input.size in 1..16384)
        val der = if (input.first() == '-'.code.toByte()) {
            val text = Charsets.US_ASCII.newDecoder().decode(java.nio.ByteBuffer.wrap(input)).toString().trim()
            val match = Regex("-----BEGIN CERTIFICATE-----\\s+([A-Za-z0-9+/=\\s]+)\\s+-----END CERTIFICATE-----").matchEntire(text)
            requireNotNull(match) { "One public certificate required" }
            Base64.getMimeDecoder().decode(match.groupValues[1])
        } else input
        val stream = ByteArrayInputStream(der)
        val cert = CertificateFactory.getInstance("X.509").generateCertificate(stream) as X509Certificate
        require(stream.available() == 0 && cert.encoded.size <= 8192)
        validate(cert)
        return cert
    }
    fun validate(cert: X509Certificate) {
        cert.checkValidity(); cert.verify(cert.publicKey)
        require(!cert.hasUnsupportedCriticalExtension())
        when (val key = cert.publicKey) {
            is ECPublicKey -> require(key.params.curve.field.fieldSize in 256..384)
            is RSAPublicKey -> require(key.modulus.bitLength() in 2048..4096)
            else -> throw IllegalArgumentException("Unsupported public key")
        }
        require(cert.sigAlgName.uppercase().replace("-", "").let { "SHA256" in it || "SHA384" in it || "SHA512" in it })
        cert.keyUsage?.let { require(it.isNotEmpty() && it[0]) }
    }
    fun context(alias: String, trust: (X509Certificate) -> Unit): SSLContext {
        ensure(alias)
        val store = keyStore()
        val cert = store.getCertificate(alias) as X509Certificate
        val key = store.getKey(alias, null) as PrivateKey
        val manager = object : X509ExtendedKeyManager() {
            override fun getPrivateKey(requested: String?) = if (requested == alias) key else null
            override fun getCertificateChain(requested: String?) = if (requested == alias) arrayOf(cert) else null
            override fun getClientAliases(type: String?, issuers: Array<out Principal>?) = if (type == key.algorithm) arrayOf(alias) else null
            override fun getServerAliases(type: String?, issuers: Array<out Principal>?) = getClientAliases(type, issuers)
            override fun chooseClientAlias(types: Array<out String>?, issuers: Array<out Principal>?, socket: java.net.Socket?) = if (types?.contains(key.algorithm) == true) alias else null
            override fun chooseEngineClientAlias(types: Array<out String>?, issuers: Array<out Principal>?, engine: SSLEngine?) = chooseClientAlias(types, issuers, null)
            override fun chooseEngineServerAlias(type: String?, issuers: Array<out Principal>?, engine: SSLEngine?) = chooseServerAlias(type, issuers, null)
            override fun chooseServerAlias(type: String?, issuers: Array<out Principal>?, socket: java.net.Socket?) = if (type == key.algorithm) alias else null
        }
        val verifier = object : X509TrustManager {
            override fun getAcceptedIssuers() = emptyArray<X509Certificate>()
            private fun check(chain: Array<out X509Certificate>?) {
                if (chain == null || chain.size != 1) throw CertificateException("One pinned identity required")
                try { trust(chain[0]); validate(chain[0]) }
                catch (_: Exception) { throw CertificateException("Pinned identity refused") }
            }
            override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?) = check(chain)
            override fun checkServerTrusted(chain: Array<out X509Certificate>?, authType: String?) = check(chain)
        }
        return SSLContext.getInstance("TLS").apply { init(arrayOf(manager), arrayOf(verifier), SecureRandom()) }
    }
}

/** Trust changes serialize with commands: after revoke returns, an old peer cannot commit. */
class PairedStore(context: Context) {
    private val file = AtomicFile(File(context.noBackupFilesDir, "paired-controller.der"))
    fun paired(): X509Certificate? = synchronized(lock) {
        try { Identity.certificate(file.openRead().use { stream ->
            val buffer = ByteArray(16385); var count = 0
            while (count < buffer.size) { val n = stream.read(buffer, count, buffer.size - count); if (n < 0) break; require(n > 0); count += n }
            require(count <= 16384); buffer.copyOf(count)
        }) }
        catch (_: java.io.FileNotFoundException) { null }
        // Corrupt/expired trust is not silently replaced or treated as a new pairing.
    }
    fun approve(cert: X509Certificate) = synchronized(lock) {
        Identity.validate(cert)
        cert.extendedKeyUsage?.let { require("1.3.6.1.5.5.7.3.2" in it) { "Client authentication certificate required" } }
        check(paired() == null) { "Remove existing trust before approval" }
        val output = file.startWrite()
        try { output.write(cert.encoded); file.finishWrite(output) }
        catch (error: Exception) { file.failWrite(output); throw error }
    }
    fun revoke() = synchronized(lock) { file.delete() }
    fun <T> authorized(pin: String, operation: () -> T): T = synchronized(lock) {
        check(Identity.pin(requireNotNull(paired())) == pin) { "Controller no longer paired" }
        operation()
    }
    fun trusts(cert: X509Certificate) = authorized(Identity.pin(cert)) { Unit }
    companion object { private val lock = Any() }
}
