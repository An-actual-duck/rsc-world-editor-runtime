package com.openrsc.server.database;

import com.openrsc.server.VerifierLifetime;
import java.util.Map;

/** No process discovery or signaling. Cleanup authority requires all leases and durable revocation. */
public final class CurrentBaseVerifierRecovery {
    public static void main(String[] arguments) {
        try {
            Map<String,String> options = VerifierLifetime.options(arguments,
                "contract", "supervision", "supervision-sha256", "evidence");
            CurrentBaseInstalledExecutionVerifier.validateRecoveryContract(VerifierLifetime.path(options.get("contract")));
            VerifierLifetime lifetime = VerifierLifetime.recovery(VerifierLifetime.path(options.get("supervision")),
                options.get("supervision-sha256"), VerifierLifetime.path(options.get("contract")));
            lifetime.recover(VerifierLifetime.path(options.get("evidence")));
            System.out.println("Current Base verifier invocation permanently closed");
        } catch (VerifierLifetime.Busy busy) {
            System.err.println("Current Base verifier recovery busy"); System.exit(3);
        } catch (Exception failure) {
            System.err.println("Current Base verifier recovery refused: " + failure.getClass().getSimpleName()); System.exit(2);
        }
    }
}
