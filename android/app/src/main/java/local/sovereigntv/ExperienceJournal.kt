package local.sovereigntv

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import android.database.sqlite.SQLiteDatabaseCorruptException
import java.io.Closeable
import java.security.MessageDigest

/** Local domain transactions. Not an exported service or an agent authorization boundary. */
class ExperienceJournal(context: Context, private val initial: () -> ExperienceRepository.Loaded) : Closeable {
    private val artwork = ArtworkStore(context)
    class Conflict(message: String) : IllegalStateException(message)
    class Capacity : IllegalStateException("Journal receipt capacity reached; owner maintenance required")
    data class Receipt(val requestId: String, val revision: Long, val previousRevision: Long, val documentSha256: String)
    private val helper = object : SQLiteOpenHelper(context, "experience-journal.sqlite3", null, 1, {
        // Android's default handler deletes corrupt databases. Preserve receipts/evidence instead.
        throw SQLiteDatabaseCorruptException("Experience journal corrupt; owner recovery required")
    }) {
        override fun onCreate(db: SQLiteDatabase) {
            db.execSQL("CREATE TABLE revisions (revision INTEGER PRIMARY KEY, document TEXT NOT NULL, recovered INTEGER NOT NULL)")
            db.execSQL("CREATE TABLE receipts (request_id TEXT PRIMARY KEY, digest TEXT NOT NULL, revision INTEGER NOT NULL, previous_revision INTEGER NOT NULL, document_sha256 TEXT NOT NULL)")
        }
        override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) = error("Unsupported journal migration")
    }

    private fun state(db: SQLiteDatabase): ExperienceRepository.Loaded = db.rawQuery(
        "SELECT revision,document,recovered FROM revisions ORDER BY revision DESC LIMIT 1", null
    ).use {
        check(it.moveToFirst())
        val document = it.getString(1)
        ExperienceRepository.Loaded(Experience.parse(document), it.getInt(2) != 0, document, it.getLong(0))
    }

    private fun initialize(db: SQLiteDatabase) {
        val exists = db.rawQuery("SELECT 1 FROM revisions LIMIT 1", null).use { it.moveToFirst() }
        if (!exists) {
            val loaded = initial()
            Experience.parse(loaded.document)
            db.execSQL("INSERT INTO revisions VALUES (1,?,?)", arrayOf<Any>(loaded.document, if (loaded.restoredDefault) 1 else 0))
        }
    }

    private fun <T> transaction(operation: (SQLiteDatabase) -> T): T {
        val db = helper.writableDatabase
        db.beginTransaction()
        try {
            initialize(db)
            val result = operation(db)
            db.setTransactionSuccessful()
            return result
        } finally { db.endTransaction() }
    }

    fun load(): ExperienceRepository.Loaded = transaction(::state)

    fun preview(baseRevision: Long, document: String): ExperienceRepository.Loaded {
        val parsed = Experience.parse(document)
        artwork.requireAssets(parsed.artworkRefs)
        return transaction { db ->
            if (state(db).revision != baseRevision) throw Conflict("Experience changed; read and rebase")
            ExperienceRepository.Loaded(parsed, document = document, revision = baseRevision)
        }
    }

    fun receipt(requestId: String): Receipt? {
        require(Regex("[A-Za-z0-9._-]{1,64}").matches(requestId))
        return transaction { db -> findReceipt(db, requestId)?.second }
    }

    private fun findReceipt(db: SQLiteDatabase, requestId: String): Pair<String, Receipt>? = db.rawQuery(
        "SELECT digest,revision,previous_revision,document_sha256 FROM receipts WHERE request_id=?", arrayOf(requestId)
    ).use { if (it.moveToFirst()) it.getString(0) to Receipt(requestId, it.getLong(1), it.getLong(2), it.getString(3)) else null }

    fun apply(requestId: String, baseRevision: Long, document: String): Receipt {
        Experience.parse(document) // Reject before starting a write transaction.
        return commit(requestId, baseRevision, "apply:$baseRevision:${sha256(document)}") { document }
    }

    fun undo(requestId: String, baseRevision: Long, restoreRevision: Long): Receipt {
        require(restoreRevision in 1 until baseRevision)
        return commit(requestId, baseRevision, "undo:$baseRevision:$restoreRevision") { db ->
            db.rawQuery("SELECT document FROM revisions WHERE revision=?", arrayOf(restoreRevision.toString())).use {
                require(it.moveToFirst()) { "Restore revision is no longer retained" }
                it.getString(0)
            }
        }
    }

    private fun commit(requestId: String, baseRevision: Long, fingerprint: String, document: (SQLiteDatabase) -> String): Receipt {
        require(Regex("[A-Za-z0-9._-]{1,64}").matches(requestId) && baseRevision > 0)
        val digest = sha256(fingerprint)
        return transaction { db ->
            val prior = findReceipt(db, requestId)
            if (prior != null) {
                if (prior.first != digest) throw Conflict("Request ID already used with different arguments")
                return@transaction prior.second
            }
            val current = state(db).revision
            if (current != baseRevision) throw Conflict("Experience changed; read and rebase")
            // Do not evict idempotency receipts and accidentally re-enable an old relative effect.
            val receiptCount = db.rawQuery("SELECT COUNT(*) FROM receipts", null).use { it.moveToFirst(); it.getLong(0) }
            if (receiptCount >= 10000) throw Capacity()
            val text = document(db)
            artwork.requireAssets(Experience.parse(text).artworkRefs)
            val revision = Math.addExact(current, 1)
            val result = Receipt(requestId, revision, current, sha256(text))
            db.execSQL("INSERT INTO revisions VALUES (?,?,0)", arrayOf<Any>(revision, text))
            db.execSQL("INSERT INTO receipts VALUES (?,?,?,?,?)", arrayOf<Any>(requestId, digest, revision, current, result.documentSha256))
            db.execSQL("DELETE FROM revisions WHERE revision < ?", arrayOf(maxOf(1L, revision - 127)))
            result
        }
    }

    override fun close() = helper.close()

    companion object {
        fun sha256(text: String): String = sha256Bytes(text.toByteArray(Charsets.UTF_8))
        fun sha256Bytes(bytes: ByteArray): String = MessageDigest.getInstance("SHA-256").digest(bytes)
            .joinToString("") { "%02x".format(it) }
    }
}
