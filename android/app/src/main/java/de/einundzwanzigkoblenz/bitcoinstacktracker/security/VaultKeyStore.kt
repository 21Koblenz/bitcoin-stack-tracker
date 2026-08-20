package de.einundzwanzigkoblenz.bitcoinstacktracker.security

import android.content.Context
import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.security.keystore.StrongBoxUnavailableException
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Device-bound envelope key for local encrypted state.
 * The AES key is non-exportable from Android Keystore. */
class VaultKeyStore(private val context: Context) {
    data class Ciphertext(
        val nonce: ByteArray,
        val bytes: ByteArray,
    )

    private val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }

    fun encrypt(plaintext: ByteArray, associatedData: ByteArray? = null): Ciphertext {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey())
        associatedData?.let(cipher::updateAAD)
        return Ciphertext(
            nonce = cipher.iv.copyOf(),
            bytes = cipher.doFinal(plaintext),
        )
    }

    fun decrypt(ciphertext: Ciphertext, associatedData: ByteArray? = null): ByteArray {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(
            Cipher.DECRYPT_MODE,
            getOrCreateKey(),
            GCMParameterSpec(128, ciphertext.nonce),
        )
        associatedData?.let(cipher::updateAAD)
        return cipher.doFinal(ciphertext.bytes)
    }

    fun deleteDeviceKey() {
        if (keyStore.containsAlias(KEY_ALIAS)) keyStore.deleteEntry(KEY_ALIAS)
    }

    private fun getOrCreateKey(): SecretKey {
        (keyStore.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }

        val strongBoxAvailable = Build.VERSION.SDK_INT >= 28 &&
            context.packageManager.hasSystemFeature("android.hardware.strongbox_keystore")
        return try {
            generateKey(preferStrongBox = strongBoxAvailable)
        } catch (_: StrongBoxUnavailableException) {
            generateKey(preferStrongBox = false)
        }
    }

    private fun generateKey(preferStrongBox: Boolean): SecretKey {
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE)
        val spec = KeyGenParameterSpec.Builder(
            KEY_ALIAS,
            KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
        )
            .setKeySize(256)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setRandomizedEncryptionRequired(true)
            .apply {
                if (Build.VERSION.SDK_INT >= 28 && preferStrongBox) {
                    setIsStrongBoxBacked(true)
                }
            }
            .build()
        generator.init(spec)
        return generator.generateKey()
    }

    companion object {
        private const val ANDROID_KEYSTORE = "AndroidKeyStore"
        private const val KEY_ALIAS = "bitcoin_stack_tracker_device_envelope_v1"
        private const val TRANSFORMATION = "AES/GCM/NoPadding"
    }
}
