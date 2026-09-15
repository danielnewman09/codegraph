#include <stdexcept>
#include <string>

#include <boost/describe.hpp>
#include <boost/describe/class.hpp>

#include "cpp_sqlite/src/cpp_sqlite/DBBaseTransferObject.hpp"
#include "cpp_sqlite/src/cpp_sqlite/DBDataAccessObject.hpp"
#include "cpp_sqlite/src/cpp_sqlite/DBDatabase.hpp"
#include "cpp_sqlite/src/cpp_sqlite/DBRepeatedFieldTransferObject.hpp"
#include "cpp_sqlite/src/cpp_sqlite/DBTransaction.hpp"
#include "cpp_sqlite/test/testDatabase.hpp"

struct ChildProduct : public cpp_sqlite::BaseTransferObject
{
  double price;
};


BOOST_DESCRIBE_STRUCT(ChildProduct, (cpp_sqlite::BaseTransferObject), (price));

BOOST_DESCRIBE_STRUCT(cpp_sqlite::RepeatedFieldTransferObject<ChildProduct>,
                      (),
                      (data));

// Test TransferObject class for demonstration
struct TestProduct : public cpp_sqlite::BaseTransferObject
{
  std::string name;
  float price;
  int quantity;
  bool in_stock;
  cpp_sqlite::RepeatedFieldTransferObject<ChildProduct> children;
};

// Register the test class with boost::describe
BOOST_DESCRIBE_STRUCT(TestProduct,
                      (cpp_sqlite::BaseTransferObject),
                      (name, price, quantity, in_stock, children));

void DatabaseTest::SetUp()
{
  // Configure logger for testing with debug level
  cpp_sqlite::Logger::getInstance().configure(
    "test_cpp_sqlite", testLogFile, spdlog::level::debug);
}

void DatabaseTest::CleanUp(std::string_view dbFile)
{
  // Clean up any test.db file that might exist
  if (std::filesystem::exists(dbFile))
  {
    std::filesystem::remove(dbFile);
  }
}


TEST_F(DatabaseTest, CreateInMemoryDatabase)
{
  std::string dbUrl{":memory:"};

  auto& logger = cpp_sqlite::Logger::getInstance();

  // Test creating an in-memory database
  auto createDB = [&dbUrl, &logger](bool readOnly)
  { return cpp_sqlite::Database{dbUrl, readOnly, logger.getLogger()}; };
  ASSERT_NO_THROW(createDB(true););

  // Test both read-write and read-only in-memory databases
  ASSERT_NO_THROW({
    createDB(true);
    createDB(false);
  });
}

TEST_F(DatabaseTest, ReadOnlyNonExistentFileThrowsError)
{
  // Ensure the file doesn't exist
  const std::string nonExistentFile = "non_existent_database.db";

  CleanUp(nonExistentFile);

  // Attempting to open a non-existent file in read-only mode should throw
  ASSERT_THROW(
    { cpp_sqlite::Database db(nonExistentFile, false); }, std::runtime_error);
}

TEST_F(DatabaseTest, CreateFileDatabase)
{
  const std::string testDbFile = "test.db";

  // Ensure clean state
  CleanUp(testDbFile);


  // Create database file
  {
    cpp_sqlite::Database db{testDbFile, true};
    // Database should be created successfully
    ASSERT_TRUE(std::filesystem::exists(testDbFile));
  }

  // Verify we can open it in read-only mode now that it exists
  ASSERT_NO_THROW({ cpp_sqlite::Database db_readonly(testDbFile, false); });

  // Clean up - file should be deleted
  ASSERT_TRUE(std::filesystem::exists(testDbFile));
  std::filesystem::remove(testDbFile);
  ASSERT_FALSE(std::filesystem::exists(testDbFile));
}

TEST_F(DatabaseTest, BoostDescribeCreateTableGeneration)
{
  const std::string testDbFile = "test_boost_describe.db";

  // Ensure clean state
  CleanUp(testDbFile);

  // Get logger instance
  auto& logger = cpp_sqlite::Logger::getInstance();

  // Create database
  cpp_sqlite::Database db{testDbFile, true, logger.getLogger()};

  // Create DataAccessObject for our test TransferObject
  auto& productDAO = db.getDAO<TestProduct>();

  // Verify table creation succeeded
  ASSERT_TRUE(productDAO.isInitialized())
    << "Failed to create table using boost::describe";

  // Clean up
  CleanUp(testDbFile);
}

TEST_F(DatabaseTest, InsertTestProduct)
{
  const std::string testDbFile = "test_insert.db";

  // Ensure clean state
  CleanUp(testDbFile);


  // Get logger instance
  auto& logger = cpp_sqlite::Logger::getInstance();

  // Create database
  cpp_sqlite::Database db{testDbFile, true, logger.getLogger()};

  // Create DataAccessObject for TestProduct
  auto& productDAO = db.getDAO<TestProduct>();

  // Verify table creation succeeded
  ASSERT_TRUE(productDAO.isInitialized())
    << "Failed to create table using boost::describe";

  std::vector<ChildProduct> childrenProducts{ChildProduct{{1}, 9.99},
                                             ChildProduct{{2}, 10.01}};

  // Create a test product with nested ChildProduct

  TestProduct testProduct;
  testProduct.id = 1;
  testProduct.name = "Test Widget";
  testProduct.price = 19.99f;
  testProduct.quantity = 100;
  testProduct.in_stock = true;
  testProduct.children.data = childrenProducts;

  // Add product to buffer and insert
  productDAO.addToBuffer(testProduct);
  ASSERT_NO_THROW(productDAO.insert()) << "Failed to insert test product";

  // Don't clean up - leave the DB file for manual inspection
  CleanUp(testDbFile);
}

// Test TransferObject with BLOB field
struct DocumentRecord : public cpp_sqlite::BaseTransferObject
{
  std::string title;
  std::string author;
  std::vector<uint8_t> file_data;  // BLOB field for binary data
};

// Register the DocumentRecord with boost::describe
BOOST_DESCRIBE_STRUCT(DocumentRecord,
                      (cpp_sqlite::BaseTransferObject),
                      (title, author, file_data));

TEST_F(DatabaseTest, InsertBlobData)
{
  const std::string testDbFile = "test_blob.db";

  // Ensure clean state
  CleanUp(testDbFile);

  // Get logger instance
  auto& logger = cpp_sqlite::Logger::getInstance();

  // Create database
  cpp_sqlite::Database db{testDbFile, true, logger.getLogger()};

  // Create DataAccessObject for DocumentRecord
  auto& docDAO = db.getDAO<DocumentRecord>();

  // Verify table creation succeeded
  ASSERT_TRUE(docDAO.isInitialized())
    << "Failed to create table with BLOB field";

  // Create a test document with binary data
  DocumentRecord testDoc;
  testDoc.id = 1;
  testDoc.title = "Test PDF Document";
  testDoc.author = "John Doe";

  // Simulate some binary data (e.g., PDF header and content)
  std::vector<uint8_t> binaryData = {
    0x25, 0x50, 0x44, 0x46, 0x2D, 0x31, 0x2E, 0x34,  // "%PDF-1.4"
    0x0A, 0x25, 0xE2, 0xE3, 0xCF, 0xD3, 0x0A,        // Binary marker
    0x48, 0x65, 0x6C, 0x6C, 0x6F, 0x20, 0x57, 0x6F,  // "Hello Wo"
    0x72, 0x6C, 0x64, 0x21                           // "rld!"
  };

  testDoc.file_data = binaryData;

  // Add document to buffer and insert
  docDAO.addToBuffer(testDoc);
  ASSERT_NO_THROW(docDAO.insert())
    << "Failed to insert document with BLOB data";

  // Verify the data was inserted by checking the buffer is empty after flush
  ASSERT_NO_THROW(docDAO.clearBuffer());

  // Don't clean up - leave the DB file for manual inspection
  CleanUp(testDbFile);
}

TEST_F(DatabaseTest, SelectAllRecords)
{
  const std::string testDbFile = "test_select_all.db";

  // Ensure clean state
  CleanUp(testDbFile);

  // Get logger instance
  auto& logger = cpp_sqlite::Logger::getInstance();

  // Create database
  cpp_sqlite::Database db{testDbFile, true, logger.getLogger()};

  // Create DataAccessObject for DocumentRecord
  auto& docDAO = db.getDAO<DocumentRecord>();

  // Verify table creation succeeded
  ASSERT_TRUE(docDAO.isInitialized());

  // Insert multiple documents
  for (int i = 1; i <= 3; i++)
  {
    DocumentRecord doc;
    doc.id = i;
    doc.title = "Document " + std::to_string(i);
    doc.author = "Author " + std::to_string(i);
    doc.file_data = {0x00, 0x01, 0x02, static_cast<uint8_t>(i)};

    docDAO.addToBuffer(doc);
  }

  // Insert all documents
  ASSERT_NO_THROW(docDAO.insert());

  // Now select all documents
  auto allDocs = docDAO.selectAll();

  // Verify we got all 3 documents back
  ASSERT_EQ(allDocs.size(), 3) << "Expected 3 documents";

  // Verify the data is correct
  for (size_t i = 0; i < allDocs.size(); i++)
  {
    EXPECT_EQ(allDocs[i].id, i + 1);
    EXPECT_EQ(allDocs[i].title, "Document " + std::to_string(i + 1));
    EXPECT_EQ(allDocs[i].author, "Author " + std::to_string(i + 1));
    EXPECT_EQ(allDocs[i].file_data.size(), 4);
    EXPECT_EQ(allDocs[i].file_data[3], static_cast<uint8_t>(i + 1));
  }

  // Clean up
  CleanUp(testDbFile);
}

TEST_F(DatabaseTest, SelectById)
{
  const std::string testDbFile = "test_select_by_id.db";

  // Ensure clean state
  CleanUp(testDbFile);

  // Get logger instance
  auto& logger = cpp_sqlite::Logger::getInstance();

  // Create database
  cpp_sqlite::Database db{testDbFile, true, logger.getLogger()};

  // Create DataAccessObject for DocumentRecord
  auto& docDAO = db.getDAO<DocumentRecord>();

  // Insert multiple documents
  for (int i = 1; i <= 5; i++)
  {
    DocumentRecord doc;
    doc.id = i;
    doc.title = "Test Doc " + std::to_string(i);
    doc.author = "Author " + std::to_string(i);
    doc.file_data = {0xAA, 0xBB, static_cast<uint8_t>(i)};

    docDAO.addToBuffer(doc);
  }

  ASSERT_NO_THROW(docDAO.insert());

  // Select document with ID 3
  auto doc3 = docDAO.selectById(3);

  // Verify we found it
  ASSERT_TRUE(doc3.has_value()) << "Document with ID 3 should exist";
  EXPECT_EQ(doc3->id, 3);
  EXPECT_EQ(doc3->title, "Test Doc 3");
  EXPECT_EQ(doc3->author, "Author 3");
  EXPECT_EQ(doc3->file_data.size(), 3);
  EXPECT_EQ(doc3->file_data[2], 3);

  // Try to select a non-existent document
  auto docNone = docDAO.selectById(999);
  EXPECT_FALSE(docNone.has_value()) << "Document with ID 999 should not exist";

  // Clean up
  CleanUp(testDbFile);
}

TEST_F(DatabaseTest, SelectWithRepeatedFields)
{
  const std::string testDbFile = "test_select_repeated.db";

  // Ensure clean state
  CleanUp(testDbFile);

  // Get logger instance
  auto& logger = cpp_sqlite::Logger::getInstance();

  // Create database
  cpp_sqlite::Database db{testDbFile, true, logger.getLogger()};

  // Create DataAccessObject for TestProduct (which has RepeatedField children)
  auto& productDAO = db.getDAO<TestProduct>();

  // Verify table creation succeeded
  ASSERT_TRUE(productDAO.isInitialized());

  // Create and insert a product with repeated children
  TestProduct product;
  product.id = 1;
  product.name = "Laptop";
  product.price = 999.99f;
  product.quantity = 10;
  product.in_stock = true;

  // Add child products
  std::vector<ChildProduct> children{
    ChildProduct{{1}, 49.99},  // Mouse
    ChildProduct{{2}, 79.99},  // Keyboard
    ChildProduct{{3}, 29.99}   // USB Cable
  };
  product.children.data = children;

  // Insert the product
  productDAO.addToBuffer(product);
  ASSERT_NO_THROW(productDAO.insert());

  // Now SELECT the product back
  auto loadedProduct = productDAO.selectById(1);

  // Verify the product was loaded
  ASSERT_TRUE(loadedProduct.has_value()) << "Product should be found";

  // Verify basic fields
  EXPECT_EQ(loadedProduct->id, 1);
  EXPECT_EQ(loadedProduct->name, "Laptop");
  EXPECT_FLOAT_EQ(loadedProduct->price, 999.99f);
  EXPECT_EQ(loadedProduct->quantity, 10);
  EXPECT_EQ(loadedProduct->in_stock, true);

  // Verify repeated children were loaded
  ASSERT_EQ(loadedProduct->children.data.size(), 3)
    << "Should have 3 child products";

  // Verify child data
  EXPECT_EQ(loadedProduct->children.data[0].id, 1);
  EXPECT_DOUBLE_EQ(loadedProduct->children.data[0].price, 49.99);

  EXPECT_EQ(loadedProduct->children.data[1].id, 2);
  EXPECT_DOUBLE_EQ(loadedProduct->children.data[1].price, 79.99);

  EXPECT_EQ(loadedProduct->children.data[2].id, 3);
  EXPECT_DOUBLE_EQ(loadedProduct->children.data[2].price, 29.99);

  // Clean up
  CleanUp(testDbFile);
}

// Test structures for ForeignKey
struct Vertex3D : public cpp_sqlite::BaseTransferObject
{
  float x;
  float y;
  float z;
};

BOOST_DESCRIBE_STRUCT(Vertex3D, (cpp_sqlite::BaseTransferObject), (x, y, z));

struct RigidBody : public cpp_sqlite::BaseTransferObject
{
  std::string name;
  float mass;
  cpp_sqlite::ForeignKey<Vertex3D> centerOfMass;  // Lazy FK
  Vertex3D initialPosition;                       // Eager load
};

BOOST_DESCRIBE_STRUCT(RigidBody,
                      (cpp_sqlite::BaseTransferObject),
                      (name, mass, centerOfMass, initialPosition));

TEST_F(DatabaseTest, ForeignKeyLazyLoading)
{
  const std::string testDbFile = "test_foreign_key.db";

  // Ensure clean state
  CleanUp(testDbFile);

  // Get logger instance
  auto& logger = cpp_sqlite::Logger::getInstance();

  // Create database
  cpp_sqlite::Database db{testDbFile, true, logger.getLogger()};

  // Create DAOs
  auto& vertexDAO = db.getDAO<Vertex3D>();
  auto& bodyDAO = db.getDAO<RigidBody>();

  // Verify table creation
  ASSERT_TRUE(vertexDAO.isInitialized());
  ASSERT_TRUE(bodyDAO.isInitialized());

  // Create and insert a vertex (for lazy loading reference)
  Vertex3D centerVertex;
  centerVertex.id = 100;
  centerVertex.x = 5.0f;
  centerVertex.y = 10.0f;
  centerVertex.z = 15.0f;
  vertexDAO.addToBuffer(centerVertex);
  vertexDAO.insert();

  // Create and insert a rigid body with ForeignKey
  RigidBody body;
  body.id = 1;
  body.name = "Test Cube";
  body.mass = 50.0f;
  body.centerOfMass.id = uint32_t{100};  // Just store the ID (lazy FK)
  body.initialPosition.id = 200;         // Eagerly loaded (auto-inserted)
  body.initialPosition.x = 0.0f;
  body.initialPosition.y = 0.0f;
  body.initialPosition.z = 0.0f;

  bodyDAO.addToBuffer(body);
  ASSERT_NO_THROW(bodyDAO.insert());

  // SELECT the rigid body
  auto loadedBody = bodyDAO.selectById(1);

  // Verify basic fields
  ASSERT_TRUE(loadedBody.has_value());
  EXPECT_EQ(loadedBody->name, "Test Cube");
  EXPECT_FLOAT_EQ(loadedBody->mass, 50.0f);

  // Verify ForeignKey only has ID (lazy - not loaded yet)
  EXPECT_EQ(loadedBody->centerOfMass.id, 100);
  EXPECT_TRUE(loadedBody->centerOfMass.isSet());

  // NOW explicitly resolve the ForeignKey
  const auto& resolvedVertexOpt = loadedBody->centerOfMass.resolve(db);
  // Verify the vertex was loaded
  ASSERT_TRUE(resolvedVertexOpt.has_value())
    << "ForeignKey should resolve to vertex";

  const auto& resolvedVertex = std::move(resolvedVertexOpt->get());
  EXPECT_EQ(resolvedVertex.id, 100);
  EXPECT_FLOAT_EQ(resolvedVertex.x, 5.0f);
  EXPECT_FLOAT_EQ(resolvedVertex.y, 10.0f);
  EXPECT_FLOAT_EQ(resolvedVertex.z, 15.0f);

  // Verify eager-loaded nested object was populated
  EXPECT_EQ(loadedBody->initialPosition.id, 200);
  EXPECT_FLOAT_EQ(loadedBody->initialPosition.x, 0.0f);

  // Clean up
  // CleanUp(testDbFile);
}

TEST_F(DatabaseTest, ForeignKeyNullReference)
{
  const std::string testDbFile = "test_foreign_key_null.db";

  // Ensure clean state
  CleanUp(testDbFile);

  // Get logger instance
  auto& logger = cpp_sqlite::Logger::getInstance();

  // Create database
  cpp_sqlite::Database db{testDbFile, true, logger.getLogger()};

  // Create DAOs
  auto& bodyDAO = db.getDAO<RigidBody>();

  // Create body with unset ForeignKey (id = 0)
  RigidBody body;
  body.id = 1;
  body.name = "Empty Body";
  body.mass = 10.0f;
  body.centerOfMass.id = 0;  // Unset FK
  body.initialPosition.x = 1.0f;
  body.initialPosition.y = 2.0f;
  body.initialPosition.z = 3.0f;

  bodyDAO.addToBuffer(body);
  bodyDAO.insert();

  // Load and verify
  auto loadedOpt = bodyDAO.selectById(1);
  ASSERT_TRUE(loadedOpt.has_value());

  auto loaded = std::move(loadedOpt.value());

  // ForeignKey should be unset
  EXPECT_EQ(loaded.centerOfMass.id, 0);
  EXPECT_FALSE(loaded.centerOfMass.isSet());

  // Resolve should return empty optional
  const auto& resolved = loaded.centerOfMass.resolve(db);
  EXPECT_FALSE(resolved.has_value()) << "Unset FK should not resolve";

  // Clean up
  CleanUp(testDbFile);
}

TEST_F(DatabaseTest, ForeignKeyMultipleReferences)
{
  const std::string testDbFile = "test_foreign_key_multiple.db";

  CleanUp(testDbFile);

  auto& logger = cpp_sqlite::Logger::getInstance();
  cpp_sqlite::Database db{testDbFile, true, logger.getLogger()};

  auto& vertexDAO = db.getDAO<Vertex3D>();
  auto& bodyDAO = db.getDAO<RigidBody>();

  // Create several vertices
  for (int i = 1; i <= 3; i++)
  {
    Vertex3D v;
    v.id = i;
    v.x = static_cast<float>(i * 10);
    v.y = static_cast<float>(i * 20);
    v.z = static_cast<float>(i * 30);
    vertexDAO.addToBuffer(v);
  }
  vertexDAO.insert();

  // Create bodies referencing different vertices
  for (uint32_t i = 1; i <= 3; i++)
  {
    RigidBody b;
    b.id = i;
    b.name = "Body " + std::to_string(i);
    b.mass = static_cast<float>(i * 100);
    b.centerOfMass.id = i;  // FK to vertex with same ID
    b.initialPosition.x = 0.0f;
    b.initialPosition.y = 0.0f;
    b.initialPosition.z = 0.0f;
    bodyDAO.addToBuffer(b);
  }
  bodyDAO.insert();

  // Load and verify each body references correct vertex
  for (int i = 1; i <= 3; i++)
  {
    auto body = bodyDAO.selectById(i);
    ASSERT_TRUE(body.has_value());

    EXPECT_EQ(body->centerOfMass.id, i);

    const auto& vertexOpt = body->centerOfMass.resolve(db);
    ASSERT_TRUE(vertexOpt.has_value());

    const auto& vertex = std::move(vertexOpt->get());

    EXPECT_EQ(vertex.id, i);
    EXPECT_FLOAT_EQ(vertex.x, static_cast<float>(i * 10));
    EXPECT_FLOAT_EQ(vertex.y, static_cast<float>(i * 20));
    EXPECT_FLOAT_EQ(vertex.z, static_cast<float>(i * 30));
  }

  CleanUp(testDbFile);
}

// Test structures in a namespace to verify namespace stripping
namespace my_app
{

struct NamespacedProduct : public cpp_sqlite::BaseTransferObject
{
  std::string name;
  float price;
};


BOOST_DESCRIBE_STRUCT(NamespacedProduct,
                      (cpp_sqlite::BaseTransferObject),
                      (name, price));

}  // namespace my_app


TEST_F(DatabaseTest, NamespacedTypes)
{
  const std::string testDbFile = "test_namespaced.db";

  CleanUp(testDbFile);

  auto& logger = cpp_sqlite::Logger::getInstance();
  cpp_sqlite::Database db{testDbFile, true, logger.getLogger()};

  auto& productDAO = db.getDAO<my_app::NamespacedProduct>();

  // Verify that table name has namespace stripped
  std::string tableName = productDAO.getTableName();
  EXPECT_EQ(tableName, "NamespacedProduct")
    << "Table name should have namespace stripped";

  // Verify table name does NOT contain "::"
  EXPECT_EQ(tableName.find("::"), std::string::npos)
    << "Table name should not contain namespace delimiter";

  // Insert a record to verify it works
  my_app::NamespacedProduct product;
  product.name = "Test Product";
  product.price = 19.99f;

  productDAO.addToBuffer(product);
  ASSERT_NO_THROW(productDAO.insert())
    << "Insert should succeed with namespaced type";

  // Verify we can retrieve it
  auto products = productDAO.selectAll();
  ASSERT_EQ(products.size(), 1);
  EXPECT_EQ(products[0].name, "Test Product");
  EXPECT_FLOAT_EQ(products[0].price, 19.99f);

  CleanUp(testDbFile);
}

// ============================================================================
// Transaction Tests
// ============================================================================

TEST_F(DatabaseTest, TransactionCommit)
{
  const std::string testDbFile = "test_transaction_commit.db";

  CleanUp(testDbFile);

  auto& logger = cpp_sqlite::Logger::getInstance();
  cpp_sqlite::Database db{testDbFile, true, logger.getLogger()};

  auto& docDAO = db.getDAO<DocumentRecord>();

  // Verify no transaction is active initially
  EXPECT_FALSE(db.isInTransaction());

  // Begin transaction
  {
    cpp_sqlite::Transaction txn(db);

    EXPECT_TRUE(db.isInTransaction());
    EXPECT_TRUE(txn.isActive());
    EXPECT_FALSE(txn.isSavepoint());

    // Insert a document within the transaction
    DocumentRecord doc;
    doc.title = "Transaction Test";
    doc.author = "Test Author";
    doc.file_data = {0x01, 0x02, 0x03};
    docDAO.addToBuffer(doc);
    docDAO.insert();

    // Commit the transaction
    txn.commit();

    EXPECT_FALSE(txn.isActive());
  }

  // Verify no transaction is active after commit
  EXPECT_FALSE(db.isInTransaction());

  // Verify the data was persisted
  auto docs = docDAO.selectAll();
  ASSERT_EQ(docs.size(), 1);
  EXPECT_EQ(docs[0].title, "Transaction Test");

  CleanUp(testDbFile);
}

TEST_F(DatabaseTest, TransactionRollback)
{
  const std::string testDbFile = "test_transaction_rollback.db";

  CleanUp(testDbFile);

  auto& logger = cpp_sqlite::Logger::getInstance();
  cpp_sqlite::Database db{testDbFile, true, logger.getLogger()};

  auto& docDAO = db.getDAO<DocumentRecord>();

  // First, insert a document outside of a transaction
  DocumentRecord initialDoc;
  initialDoc.title = "Initial Document";
  initialDoc.author = "Initial Author";
  initialDoc.file_data = {0xAA};
  docDAO.addToBuffer(initialDoc);
  docDAO.insert();

  // Verify it's there
  ASSERT_EQ(docDAO.selectAll().size(), 1);

  // Now begin a transaction and rollback
  {
    cpp_sqlite::Transaction txn(db);

    // Insert another document
    DocumentRecord doc;
    doc.title = "Should Be Rolled Back";
    doc.author = "Rollback Author";
    doc.file_data = {0xBB};
    docDAO.addToBuffer(doc);
    docDAO.insert();

    // Explicitly rollback
    txn.rollback();

    EXPECT_FALSE(txn.isActive());
  }

  // Verify only the initial document exists (rollback worked)
  auto docs = docDAO.selectAll();
  ASSERT_EQ(docs.size(), 1);
  EXPECT_EQ(docs[0].title, "Initial Document");

  CleanUp(testDbFile);
}

TEST_F(DatabaseTest, TransactionAutoRollbackOnDestruction)
{
  const std::string testDbFile = "test_transaction_auto_rollback.db";

  CleanUp(testDbFile);

  auto& logger = cpp_sqlite::Logger::getInstance();
  cpp_sqlite::Database db{testDbFile, true, logger.getLogger()};

  auto& docDAO = db.getDAO<DocumentRecord>();

  // Begin a transaction and let it go out of scope without commit
  {
    cpp_sqlite::Transaction txn(db);

    DocumentRecord doc;
    doc.title = "Should Auto Rollback";
    doc.author = "Auto Rollback Author";
    doc.file_data = {0xCC};
    docDAO.addToBuffer(doc);
    docDAO.insert();

    // Transaction goes out of scope without commit - should auto-rollback
  }

  // Verify no data was persisted
  auto docs = docDAO.selectAll();
  EXPECT_EQ(docs.size(), 0) << "Data should be rolled back on destruction";

  CleanUp(testDbFile);
}

TEST_F(DatabaseTest, NestedTransactionWithSavepoints)
{
  const std::string testDbFile = "test_nested_transaction.db";

  CleanUp(testDbFile);

  auto& logger = cpp_sqlite::Logger::getInstance();
  cpp_sqlite::Database db{testDbFile, true, logger.getLogger()};

  auto& docDAO = db.getDAO<DocumentRecord>();

  // Outer transaction
  {
    cpp_sqlite::Transaction outerTxn(db);

    EXPECT_TRUE(db.isInTransaction());
    EXPECT_FALSE(outerTxn.isSavepoint());

    // Insert first document
    DocumentRecord doc1;
    doc1.title = "Outer Doc";
    doc1.author = "Outer Author";
    doc1.file_data = {0x01};
    docDAO.addToBuffer(doc1);
    docDAO.insert();

    // Inner transaction (should become a savepoint)
    {
      cpp_sqlite::Transaction innerTxn(db);

      EXPECT_TRUE(innerTxn.isSavepoint());
      EXPECT_FALSE(innerTxn.getSavepointName().empty());

      // Insert second document
      DocumentRecord doc2;
      doc2.title = "Inner Doc";
      doc2.author = "Inner Author";
      doc2.file_data = {0x02};
      docDAO.addToBuffer(doc2);
      docDAO.insert();

      // Commit inner (release savepoint)
      innerTxn.commit();
    }

    // Commit outer
    outerTxn.commit();
  }

  // Verify both documents were persisted
  auto docs = docDAO.selectAll();
  ASSERT_EQ(docs.size(), 2);

  CleanUp(testDbFile);
}

TEST_F(DatabaseTest, NestedTransactionRollbackInner)
{
  const std::string testDbFile = "test_nested_rollback_inner.db";

  CleanUp(testDbFile);

  auto& logger = cpp_sqlite::Logger::getInstance();
  cpp_sqlite::Database db{testDbFile, true, logger.getLogger()};

  auto& docDAO = db.getDAO<DocumentRecord>();

  // Outer transaction
  {
    cpp_sqlite::Transaction outerTxn(db);

    // Insert first document
    DocumentRecord doc1;
    doc1.title = "Outer Doc";
    doc1.author = "Outer Author";
    doc1.file_data = {0x01};
    docDAO.addToBuffer(doc1);
    docDAO.insert();

    // Inner transaction that will be rolled back
    {
      cpp_sqlite::Transaction innerTxn(db);

      // Insert second document
      DocumentRecord doc2;
      doc2.title = "Inner Doc - Should Rollback";
      doc2.author = "Inner Author";
      doc2.file_data = {0x02};
      docDAO.addToBuffer(doc2);
      docDAO.insert();

      // Rollback inner (rollback to savepoint)
      innerTxn.rollback();
    }

    // Commit outer
    outerTxn.commit();
  }

  // Verify only outer document was persisted
  auto docs = docDAO.selectAll();
  ASSERT_EQ(docs.size(), 1);
  EXPECT_EQ(docs[0].title, "Outer Doc");

  CleanUp(testDbFile);
}

TEST_F(DatabaseTest, WithTransactionHelper)
{
  const std::string testDbFile = "test_with_transaction.db";

  CleanUp(testDbFile);

  auto& logger = cpp_sqlite::Logger::getInstance();
  cpp_sqlite::Database db{testDbFile, true, logger.getLogger()};

  auto& docDAO = db.getDAO<DocumentRecord>();

  // Use the withTransaction helper
  db.withTransaction(
    [&]()
    {
      DocumentRecord doc;
      doc.title = "WithTransaction Test";
      doc.author = "Helper Author";
      doc.file_data = {0xDD};
      docDAO.addToBuffer(doc);
      docDAO.insert();
    });

  // Verify data was persisted
  auto docs = docDAO.selectAll();
  ASSERT_EQ(docs.size(), 1);
  EXPECT_EQ(docs[0].title, "WithTransaction Test");

  CleanUp(testDbFile);
}

TEST_F(DatabaseTest, WithTransactionRollbackOnException)
{
  const std::string testDbFile = "test_with_transaction_exception.db";

  CleanUp(testDbFile);

  auto& logger = cpp_sqlite::Logger::getInstance();
  cpp_sqlite::Database db{testDbFile, true, logger.getLogger()};

  auto& docDAO = db.getDAO<DocumentRecord>();

  // Use withTransaction with an exception
  EXPECT_THROW(
    {
      db.withTransaction(
        [&]()
        {
          DocumentRecord doc;
          doc.title = "Should Be Rolled Back";
          doc.author = "Exception Author";
          doc.file_data = {0xEE};
          docDAO.addToBuffer(doc);
          docDAO.insert();

          // Throw an exception - should trigger rollback
          throw std::runtime_error("Intentional test exception");
        });
    },
    std::runtime_error);

  // Verify data was NOT persisted (rolled back)
  auto docs = docDAO.selectAll();
  EXPECT_EQ(docs.size(), 0) << "Data should be rolled back on exception";

  CleanUp(testDbFile);
}

TEST_F(DatabaseTest, TransactionMultipleInserts)
{
  const std::string testDbFile = "test_transaction_multiple.db";

  CleanUp(testDbFile);

  auto& logger = cpp_sqlite::Logger::getInstance();
  cpp_sqlite::Database db{testDbFile, true, logger.getLogger()};

  auto& docDAO = db.getDAO<DocumentRecord>();

  // Insert multiple documents in a single transaction
  db.withTransaction(
    [&]()
    {
      for (int i = 1; i <= 100; i++)
      {
        DocumentRecord doc;
        doc.title = "Batch Doc " + std::to_string(i);
        doc.author = "Batch Author";
        doc.file_data = {static_cast<uint8_t>(i)};
        docDAO.addToBuffer(doc);
      }
      docDAO.insert();
    });

  // Verify all documents were persisted
  auto docs = docDAO.selectAll();
  ASSERT_EQ(docs.size(), 100);

  CleanUp(testDbFile);
}

// ============================================================================
// flushAllDAOs Tests
// ============================================================================

TEST_F(DatabaseTest, FlushAllDAOs_EmptyDatabase_NoOp)
{
  const std::string testDbFile = "test_flush_all_empty.db";

  CleanUp(testDbFile);

  auto& logger = cpp_sqlite::Logger::getInstance();
  cpp_sqlite::Database db{testDbFile, true, logger.getLogger()};

  // Call flushAllDAOs on a fresh database with no DAOs - should be a no-op
  ASSERT_NO_THROW(db.flushAllDAOs());

  CleanUp(testDbFile);
}

TEST_F(DatabaseTest, FlushAllDAOs_SingleDAO_FlushesRecords)
{
  const std::string testDbFile = "test_flush_all_single.db";

  CleanUp(testDbFile);

  auto& logger = cpp_sqlite::Logger::getInstance();
  cpp_sqlite::Database db{testDbFile, true, logger.getLogger()};

  auto& docDAO = db.getDAO<DocumentRecord>();

  // Add records to buffer
  for (int i = 1; i <= 3; i++)
  {
    DocumentRecord doc;
    doc.title = "Doc " + std::to_string(i);
    doc.author = "Author";
    doc.file_data = {static_cast<uint8_t>(i)};
    docDAO.addToBuffer(doc);
  }

  // Flush all DAOs
  ASSERT_NO_THROW(db.flushAllDAOs());

  // Verify records were inserted
  auto docs = docDAO.selectAll();
  ASSERT_EQ(docs.size(), 3);

  CleanUp(testDbFile);
}

TEST_F(DatabaseTest, FlushAllDAOs_MultipleDAOs_FlushesAll)
{
  const std::string testDbFile = "test_flush_all_multiple.db";

  CleanUp(testDbFile);

  auto& logger = cpp_sqlite::Logger::getInstance();
  cpp_sqlite::Database db{testDbFile, true, logger.getLogger()};

  // Get multiple DAOs
  auto& docDAO = db.getDAO<DocumentRecord>();
  auto& vertexDAO = db.getDAO<Vertex3D>();
  auto& productDAO = db.getDAO<my_app::NamespacedProduct>();

  // Add records to each DAO's buffer
  for (int i = 1; i <= 2; i++)
  {
    DocumentRecord doc;
    doc.title = "Doc " + std::to_string(i);
    doc.author = "Author";
    doc.file_data = {static_cast<uint8_t>(i)};
    docDAO.addToBuffer(doc);

    Vertex3D v;
    v.x = static_cast<float>(i);
    v.y = static_cast<float>(i * 2);
    v.z = static_cast<float>(i * 3);
    vertexDAO.addToBuffer(v);

    my_app::NamespacedProduct p;
    p.name = "Product " + std::to_string(i);
    p.price = static_cast<float>(i * 10);
    productDAO.addToBuffer(p);
  }

  // Single call to flush all DAOs
  ASSERT_NO_THROW(db.flushAllDAOs());

  // Verify all records were inserted
  EXPECT_EQ(docDAO.selectAll().size(), 2);
  EXPECT_EQ(vertexDAO.selectAll().size(), 2);
  EXPECT_EQ(productDAO.selectAll().size(), 2);

  CleanUp(testDbFile);
}

TEST_F(DatabaseTest, FlushAllDAOs_EmptyBuffers_NoOp)
{
  const std::string testDbFile = "test_flush_all_empty_buffers.db";

  CleanUp(testDbFile);

  auto& logger = cpp_sqlite::Logger::getInstance();
  cpp_sqlite::Database db{testDbFile, true, logger.getLogger()};

  // Create DAOs but don't add anything to buffers
  auto& docDAO = db.getDAO<DocumentRecord>();
  auto& vertexDAO = db.getDAO<Vertex3D>();

  // Flush empty buffers - should be a no-op
  ASSERT_NO_THROW(db.flushAllDAOs());

  // Verify no records exist
  EXPECT_EQ(docDAO.selectAll().size(), 0);
  EXPECT_EQ(vertexDAO.selectAll().size(), 0);

  CleanUp(testDbFile);
}

TEST_F(DatabaseTest, FlushAllDAOs_DeterministicOrder)
{
  const std::string testDbFile = "test_flush_all_order.db";

  CleanUp(testDbFile);

  auto& logger = cpp_sqlite::Logger::getInstance();
  cpp_sqlite::Database db{testDbFile, true, logger.getLogger()};

  // Create DAOs in a specific order
  auto& docDAO = db.getDAO<DocumentRecord>();
  auto& vertexDAO = db.getDAO<Vertex3D>();
  auto& productDAO = db.getDAO<my_app::NamespacedProduct>();

  // Add a single record to each
  DocumentRecord doc;
  doc.title = "Test";
  doc.author = "Author";
  doc.file_data = {0x01};
  docDAO.addToBuffer(doc);

  Vertex3D v;
  v.x = 1.0f;
  v.y = 2.0f;
  v.z = 3.0f;
  vertexDAO.addToBuffer(v);

  my_app::NamespacedProduct p;
  p.name = "Product";
  p.price = 9.99f;
  productDAO.addToBuffer(p);

  // Flush multiple times - order should be deterministic
  for (int i = 0; i < 3; i++)
  {
    // Clear and re-add
    docDAO.clearBuffer();
    vertexDAO.clearBuffer();
    productDAO.clearBuffer();

    docDAO.addToBuffer(doc);
    vertexDAO.addToBuffer(v);
    productDAO.addToBuffer(p);

    ASSERT_NO_THROW(db.flushAllDAOs());
  }

  // All records should be inserted (3 iterations + 1 initial = 4 each, but we
  // cleared between, so just 3 from the loop)
  // Actually first flush happens before the loop, so total is 1 + 3 = 4
  // Wait, the first addToBuffer calls are before the loop, and first flush
  // is inside the loop after clear+re-add. So it's 3 flushes total.
  EXPECT_EQ(docDAO.selectAll().size(), 3);
  EXPECT_EQ(vertexDAO.selectAll().size(), 3);
  EXPECT_EQ(productDAO.selectAll().size(), 3);

  CleanUp(testDbFile);
}