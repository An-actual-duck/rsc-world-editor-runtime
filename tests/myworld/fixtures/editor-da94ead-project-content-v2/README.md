# Reviewed Editor bundle-v2 fixture

`bundle/` is a byte-for-byte mirror of the corrected project-content-bundle-v2
contract reviewed at Editor commit `da94ead`. It was copied from the immutable
staging directory supplied to the runtime worker. `SHA256SUMS` is the checksum
inventory supplied beside that fixture; the compatibility test resolves its
staged `/bundle/` suffix against this checked-in mirror.

Do not regenerate this fixture from runtime test helpers. Producer/consumer
compatibility is proven by passing these exact bytes independently through the
server and client loaders.
