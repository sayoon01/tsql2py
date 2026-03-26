"""
퓨샷(Few-Shot) 예시 모음
MS SQL Stored Procedure → Python 변환 패턴별 예시
"""

# ──────────────────────────────────────────────
#  예시 1: 단순 SELECT (파라미터 + 기본값)
# ──────────────────────────────────────────────
EXAMPLE_1_SQL = """\
CREATE PROCEDURE GetActiveUsers
    @MinAge INT = 18,
    @MaxResults INT = 100
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP(@MaxResults) UserID, UserName, Email, Age
    FROM Users
    WHERE IsActive = 1 AND Age >= @MinAge
    ORDER BY UserName;
END"""

EXAMPLE_1_PYTHON = """\
import pyodbc
import pandas as pd


def get_active_users(
    conn_str: str,
    min_age: int = 18,
    max_results: int = 100,
) -> pd.DataFrame:
    \"\"\"활성 사용자 목록을 조회합니다.\"\"\"
    query = \"\"\"
        SELECT TOP(?) UserID, UserName, Email, Age
        FROM Users
        WHERE IsActive = 1 AND Age >= ?
        ORDER BY UserName
    \"\"\"
    with pyodbc.connect(conn_str) as conn:
        df = pd.read_sql(query, conn, params=[max_results, min_age])
    return df"""

# ──────────────────────────────────────────────
#  예시 2: 트랜잭션 + OUTPUT 파라미터 + TRY/CATCH
# ──────────────────────────────────────────────
EXAMPLE_2_SQL = """\
CREATE PROCEDURE UpdateOrderStatus
    @OrderID      INT,
    @NewStatus    NVARCHAR(50),
    @UpdatedBy    NVARCHAR(100),
    @UpdatedCount INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        BEGIN TRANSACTION;

        UPDATE Orders
        SET Status       = @NewStatus,
            ModifiedBy   = @UpdatedBy,
            ModifiedDate = GETDATE()
        WHERE OrderID = @OrderID;

        SET @UpdatedCount = @@ROWCOUNT;

        INSERT INTO OrderAuditLog (OrderID, OldStatus, NewStatus, ChangedBy, ChangedDate)
        SELECT @OrderID, Status, @NewStatus, @UpdatedBy, GETDATE()
        FROM Orders WHERE OrderID = @OrderID;

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;

        DECLARE @ErrorMsg NVARCHAR(4000) = ERROR_MESSAGE();
        RAISERROR(@ErrorMsg, 16, 1);
    END CATCH
END"""

EXAMPLE_2_PYTHON = """\
import pyodbc
from datetime import datetime
from dataclasses import dataclass


@dataclass
class UpdateResult:
    updated_count: int
    success: bool
    error_message: str | None = None


def update_order_status(
    conn_str: str,
    order_id: int,
    new_status: str,
    updated_by: str,
) -> UpdateResult:
    \"\"\"주문 상태를 변경하고 감사 로그를 기록합니다.\"\"\"
    with pyodbc.connect(conn_str) as conn:
        cursor = conn.cursor()
        try:
            # 상태 업데이트
            cursor.execute(
                \"\"\"
                UPDATE Orders
                SET Status = ?, ModifiedBy = ?, ModifiedDate = ?
                WHERE OrderID = ?
                \"\"\",
                new_status, updated_by, datetime.now(), order_id,
            )
            updated_count = cursor.rowcount

            # 감사 로그 기록
            cursor.execute(
                \"\"\"
                INSERT INTO OrderAuditLog
                    (OrderID, OldStatus, NewStatus, ChangedBy, ChangedDate)
                SELECT ?, Status, ?, ?, ?
                FROM Orders WHERE OrderID = ?
                \"\"\",
                order_id, new_status, updated_by, datetime.now(), order_id,
            )
            conn.commit()
            return UpdateResult(updated_count=updated_count, success=True)

        except Exception as e:
            conn.rollback()
            return UpdateResult(
                updated_count=0, success=False, error_message=str(e)
            )"""

# ──────────────────────────────────────────────
#  예시 3: 임시 테이블 + 커서 루프 + 동적 처리
# ──────────────────────────────────────────────
EXAMPLE_3_SQL = """\
CREATE PROCEDURE ProcessMonthlyReport
    @Year  INT,
    @Month INT
AS
BEGIN
    SET NOCOUNT ON;

    -- 임시 테이블
    CREATE TABLE #MonthlySales (
        ProductID    INT,
        ProductName  NVARCHAR(200),
        TotalQty     INT,
        TotalRevenue DECIMAL(18,2)
    );

    INSERT INTO #MonthlySales
    SELECT p.ProductID, p.ProductName, SUM(od.Quantity), SUM(od.Quantity * od.UnitPrice)
    FROM OrderDetails od
    JOIN Orders o ON od.OrderID = o.OrderID
    JOIN Products p ON od.ProductID = p.ProductID
    WHERE YEAR(o.OrderDate) = @Year AND MONTH(o.OrderDate) = @Month
    GROUP BY p.ProductID, p.ProductName;

    -- 커서로 인기 상품 마킹
    DECLARE @PID INT, @Qty INT;
    DECLARE cur CURSOR LOCAL FAST_FORWARD FOR
        SELECT ProductID, TotalQty FROM #MonthlySales WHERE TotalQty > 100;

    OPEN cur;
    FETCH NEXT FROM cur INTO @PID, @Qty;
    WHILE @@FETCH_STATUS = 0
    BEGIN
        UPDATE Products SET IsPopular = 1, LastPopularDate = GETDATE()
        WHERE ProductID = @PID;
        FETCH NEXT FROM cur INTO @PID, @Qty;
    END
    CLOSE cur;
    DEALLOCATE cur;

    -- 결과 반환
    SELECT * FROM #MonthlySales ORDER BY TotalRevenue DESC;
    DROP TABLE #MonthlySales;
END"""

EXAMPLE_3_PYTHON = """\
import pyodbc
import pandas as pd
from datetime import datetime


def process_monthly_report(
    conn_str: str,
    year: int,
    month: int,
) -> pd.DataFrame:
    \"\"\"월간 매출 리포트를 생성하고 인기 상품을 마킹합니다.\"\"\"
    with pyodbc.connect(conn_str) as conn:
        cursor = conn.cursor()

        # 임시 테이블 → DataFrame
        monthly_sales = pd.read_sql(
            \"\"\"
            SELECT p.ProductID, p.ProductName,
                   SUM(od.Quantity)                AS TotalQty,
                   SUM(od.Quantity * od.UnitPrice) AS TotalRevenue
            FROM OrderDetails od
            JOIN Orders o  ON od.OrderID  = o.OrderID
            JOIN Products p ON od.ProductID = p.ProductID
            WHERE YEAR(o.OrderDate) = ? AND MONTH(o.OrderDate) = ?
            GROUP BY p.ProductID, p.ProductName
            \"\"\",
            conn,
            params=[year, month],
        )

        # 커서 루프 → 벡터화 일괄 UPDATE
        popular_ids = monthly_sales.loc[
            monthly_sales["TotalQty"] > 100, "ProductID"
        ].tolist()

        if popular_ids:
            placeholders = ",".join("?" * len(popular_ids))
            cursor.execute(
                f\"\"\"
                UPDATE Products
                SET IsPopular = 1, LastPopularDate = ?
                WHERE ProductID IN ({placeholders})
                \"\"\",
                [datetime.now()] + popular_ids,
            )
            conn.commit()

        return monthly_sales.sort_values("TotalRevenue", ascending=False)"""

# ──────────────────────────────────────────────
#  예시 4: 동적 SQL + 페이징
# ──────────────────────────────────────────────
EXAMPLE_4_SQL = """\
CREATE PROCEDURE SearchProducts
    @Keyword    NVARCHAR(100) = NULL,
    @CategoryID INT           = NULL,
    @SortBy     NVARCHAR(50)  = 'ProductName',
    @PageNum    INT           = 1,
    @PageSize   INT           = 20,
    @TotalCount INT           OUTPUT
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @SQL   NVARCHAR(MAX),
            @Where NVARCHAR(MAX) = ' WHERE 1=1 ';

    IF @Keyword IS NOT NULL
        SET @Where += ' AND ProductName LIKE ''%'' + @Keyword + ''%'' ';
    IF @CategoryID IS NOT NULL
        SET @Where += ' AND CategoryID = @CategoryID ';

    -- 총 건수
    SET @SQL = N'SELECT @cnt = COUNT(*) FROM Products' + @Where;
    EXEC sp_executesql @SQL,
        N'@Keyword NVARCHAR(100), @CategoryID INT, @cnt INT OUTPUT',
        @Keyword, @CategoryID, @TotalCount OUTPUT;

    -- 페이징 조회
    SET @SQL = N'SELECT ProductID, ProductName, Price, CategoryID
                 FROM Products' + @Where +
                N' ORDER BY ' + QUOTENAME(@SortBy) +
                N' OFFSET @Offset ROWS FETCH NEXT @PageSize ROWS ONLY';

    EXEC sp_executesql @SQL,
        N'@Keyword NVARCHAR(100), @CategoryID INT, @Offset INT, @PageSize INT',
        @Keyword, @CategoryID, (@PageNum - 1) * @PageSize, @PageSize;
END"""

EXAMPLE_4_PYTHON = """\
import pyodbc
import pandas as pd
from dataclasses import dataclass


@dataclass
class SearchResult:
    data: pd.DataFrame
    total_count: int
    page_num: int
    page_size: int

    @property
    def total_pages(self) -> int:
        return -(-self.total_count // self.page_size)  # ceil division


def search_products(
    conn_str: str,
    keyword: str | None = None,
    category_id: int | None = None,
    sort_by: str = "ProductName",
    page_num: int = 1,
    page_size: int = 20,
) -> SearchResult:
    \"\"\"상품을 검색하고 페이징된 결과를 반환합니다.\"\"\"
    # 허용된 정렬 컬럼 (SQL Injection 방지)
    allowed_sorts = {"ProductID", "ProductName", "Price", "CategoryID"}
    if sort_by not in allowed_sorts:
        raise ValueError(f"정렬 컬럼은 {allowed_sorts} 중 하나여야 합니다.")

    conditions: list[str] = []
    params: list = []

    if keyword is not None:
        conditions.append("ProductName LIKE ?")
        params.append(f"%{keyword}%")
    if category_id is not None:
        conditions.append("CategoryID = ?")
        params.append(category_id)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    with pyodbc.connect(conn_str) as conn:
        # 총 건수
        count_row = pd.read_sql(
            f"SELECT COUNT(*) AS cnt FROM Products WHERE {where_clause}",
            conn, params=params,
        )
        total_count = int(count_row["cnt"].iloc[0])

        # 페이징 조회
        offset = (page_num - 1) * page_size
        data = pd.read_sql(
            f\"\"\"
            SELECT ProductID, ProductName, Price, CategoryID
            FROM Products
            WHERE {where_clause}
            ORDER BY {sort_by}
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
            \"\"\",
            conn,
            params=params + [offset, page_size],
        )

    return SearchResult(
        data=data, total_count=total_count,
        page_num=page_num, page_size=page_size,
    )"""

# ──────────────────────────────────────────────
#  예시 5: MERGE (UPSERT) 패턴
# ──────────────────────────────────────────────
EXAMPLE_5_SQL = """\
CREATE PROCEDURE UpsertCustomer
    @CustomerID   INT,
    @CustomerName NVARCHAR(200),
    @Email        NVARCHAR(200),
    @Phone        NVARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;

    MERGE INTO Customers AS target
    USING (SELECT @CustomerID AS CustomerID) AS source
    ON target.CustomerID = source.CustomerID
    WHEN MATCHED THEN
        UPDATE SET
            CustomerName = @CustomerName,
            Email        = @Email,
            Phone        = @Phone,
            ModifiedDate = GETDATE()
    WHEN NOT MATCHED THEN
        INSERT (CustomerID, CustomerName, Email, Phone, CreatedDate)
        VALUES (@CustomerID, @CustomerName, @Email, @Phone, GETDATE());
END"""

EXAMPLE_5_PYTHON = """\
import pyodbc
from datetime import datetime


def upsert_customer(
    conn_str: str,
    customer_id: int,
    customer_name: str,
    email: str,
    phone: str,
) -> str:
    \"\"\"고객 정보를 UPSERT(있으면 수정, 없으면 삽입)합니다.\"\"\"
    with pyodbc.connect(conn_str) as conn:
        cursor = conn.cursor()
        now = datetime.now()

        # 존재 여부 확인
        cursor.execute(
            "SELECT COUNT(*) FROM Customers WHERE CustomerID = ?",
            customer_id,
        )
        exists = cursor.fetchone()[0] > 0

        if exists:
            cursor.execute(
                \"\"\"
                UPDATE Customers
                SET CustomerName = ?, Email = ?, Phone = ?, ModifiedDate = ?
                WHERE CustomerID = ?
                \"\"\",
                customer_name, email, phone, now, customer_id,
            )
            action = "updated"
        else:
            cursor.execute(
                \"\"\"
                INSERT INTO Customers
                    (CustomerID, CustomerName, Email, Phone, CreatedDate)
                VALUES (?, ?, ?, ?, ?)
                \"\"\",
                customer_id, customer_name, email, phone, now,
            )
            action = "inserted"

        conn.commit()
    return action"""


# ──────────────────────────────────────────────
#  전체 예시 리스트
# ──────────────────────────────────────────────
ALL_EXAMPLES = [
    {"tag": "simple_select",   "sql": EXAMPLE_1_SQL, "python": EXAMPLE_1_PYTHON},
    {"tag": "transaction",     "sql": EXAMPLE_2_SQL, "python": EXAMPLE_2_PYTHON},
    {"tag": "temp_table",      "sql": EXAMPLE_3_SQL, "python": EXAMPLE_3_PYTHON},
    {"tag": "dynamic_sql",     "sql": EXAMPLE_4_SQL, "python": EXAMPLE_4_PYTHON},
    {"tag": "merge_upsert",    "sql": EXAMPLE_5_SQL, "python": EXAMPLE_5_PYTHON},
]
