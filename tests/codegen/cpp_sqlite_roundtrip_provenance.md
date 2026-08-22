# cpp-sqlite Round-Trip Fixture Provenance

The byte-fidelity and graph-fixpoint suites regenerate the committed
cpp-sqlite production tree and compare it against the read-only golden
source copies under `tests/unit_test_data/cpp_sqlite_impl_src/`.  This
file records exactly which source revision those copies came from, so a
refresh is a deliberate, explicit action — never a silent side effect of a
test run.

## Canonical source

- Repository: `https://github.com/danielnewman09/cpp-sqlite` (upstream)
- Local checkout: `../cpp-sqlite`
- Fixture sync source (sister repo): `../Doxygen-Dependency-Parser/tests/fixtures/cpp-sqlite`
- `scripts/sync_codegen_fixtures.py pull` is the only supported refresh
  entry point for the source copies and implementation-bearing exports.

## Source revision

The committed source copies match the upstream tree at the revision last
adopted via `pull`.  Record the upstream revision in `pull` output; the
fixture-copy hashes below pin the exact bytes regardless of VCS state.

## Production manifest (14 files)

```
tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBBaseTransferObject.hpp
tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBDAOBase.hpp
tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBDataAccessObject.cpp
tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBDataAccessObject.hpp
tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBDatabase.cpp
tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBDatabase.hpp
tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBForeignKey.hpp
tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBRepeatedFieldTransferObject.hpp
tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBTraits.hpp
tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBTransaction.cpp
tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBTransaction.hpp
tests/fixtures/cpp-sqlite/cpp_sqlite/src/utils/Logger.cpp
tests/fixtures/cpp-sqlite/cpp_sqlite/src/utils/Logger.hpp
tests/fixtures/cpp-sqlite/cpp_sqlite/src/utils/StringUtils.hpp
```

The two GoogleTest files (`test/testDatabase.hpp`, `test/testDatabase.cpp`)
are outside source byte-fidelity (constraint 3) and serve as later
behavioral evidence.

## Pinned canonical formatter

- clang-format major version: 17
- Configuration: `tests/codegen/cpp_sqlite.clang-format`
- Comparison policy: LF plus exactly one final newline after canonical
  formatting (the final-newline boundary is not a semantic model element).

## Golden source-copy hashes (SHA-256)

Recorded 2026-08-16.  `sync_codegen_fixtures.py check` verifies the
committed source copies against these hashes; a drift means the fixture was
changed or re-synced without updating this file.

```
7b10f133d7574b541f10226cb55e52e8e432c2a3c18abc6e9b2ef0d70458fcd4  tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBBaseTransferObject.hpp
720066540706875c795b4bc07e6ba80a2e58e3ed9b76a4806f305bd874368ca1  tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBDAOBase.hpp
267be95bb6c1c10105347d106bbdbf5d111f5d1804005f44822e63b414942dbf  tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBDataAccessObject.cpp
62e6d93943285cceec1a2e38e3216cb82d6b562241ebd838a2b31beda594e0c4  tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBDataAccessObject.hpp
c1398655b252a6f8bf01dc0a92f88813fe13728e01e453ad46e5407e13a8797d  tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBDatabase.cpp
0ca792dbcbac69919ff012fce576681d42b4ee18c7499ad72e21b364fec0ffb9  tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBDatabase.hpp
6205b52bbf54b03309dac0c1678a0229664a026417c77c6b569f3d274062a238  tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBForeignKey.hpp
1735aa3befc5846b5bbc0d916ebf44416c9189ed90c8f45d52c00370d34a5407  tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBRepeatedFieldTransferObject.hpp
c8a9addfede0d944063e62f3a7073346089efc3f9aa51be085423a3839e616f1  tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBTraits.hpp
7910a7211272bb915e1c2f5e4bb88ce6efc07465ef47ec176ce9622350bb937e  tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBTransaction.cpp
457472178c2112ca38afaa948ce933d2abfe12926e8eed264d21fc1583ef873e  tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBTransaction.hpp
b05acd60c88f64de307217090761a1953673826e1acb9fcb366605d7afce2fb7  tests/fixtures/cpp-sqlite/cpp_sqlite/src/utils/Logger.cpp
b0162bf93fb3db2b8c43ae3ed636e5084d0864b88b8f33b5d80294dc89a471a0  tests/fixtures/cpp-sqlite/cpp_sqlite/src/utils/Logger.hpp
6251431759a4781119902b1745ac78e3d133f4cc8327c4a5f2e0bdee3d7f7377  tests/fixtures/cpp-sqlite/cpp_sqlite/src/utils/StringUtils.hpp
```

## Refresh

```bash
python scripts/sync_codegen_fixtures.py pull    # adopt the sister repo's fixture
python scripts/sync_codegen_fixtures.py check   # verify fixtures + provenance
```

`pull` prints every changed target and re-records the provenance hashes;
`check` never modifies anything.
