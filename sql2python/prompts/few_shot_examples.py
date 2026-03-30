"""
퓨샷(Few-Shot) 예시 모음
MS SQL Stored Procedure → Python 변환 패턴별 예시.

ALL_EXAMPLES 에 SQL/파이썬 쌍 10개가 있으며, prompts.template 에서
--num-examples(1~10)만큼 앞에서부터 잘라 프롬프트에 넣습니다.
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
    \"\"\"활성 사용자 목록 조회\"\"\"

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

    DECLARE @OldStatus NVARCHAR(50);

    BEGIN TRY
        BEGIN TRANSACTION;

        -- 기존 상태 조회
        SELECT @OldStatus = Status
        FROM Orders
        WHERE OrderID = @OrderID;

        -- 주문이 없으면 예외 처리
        IF @OldStatus IS NULL
        BEGIN
            RAISERROR('해당 OrderID의 주문이 존재하지 않습니다.', 16, 1);
        END

        -- 상태 업데이트
        UPDATE Orders
        SET Status       = @NewStatus,
            ModifiedBy   = @UpdatedBy,
            ModifiedDate = GETDATE()
        WHERE OrderID = @OrderID;

        SET @UpdatedCount = @@ROWCOUNT;

        -- 감사 로그 기록
        INSERT INTO OrderAuditLog
            (OrderID, OldStatus, NewStatus, ChangedBy, ChangedDate)
        VALUES
            (@OrderID, @OldStatus, @NewStatus, @UpdatedBy, GETDATE());

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
        conn.autocommit = False
        cursor = conn.cursor()

        try:
            # 1. 기존 상태 조회
            cursor.execute(
                \"\"\"
                SELECT Status
                FROM Orders
                WHERE OrderID = ?
                \"\"\",
                order_id,
            )
            row = cursor.fetchone()

            if row is None:
                raise ValueError("해당 OrderID의 주문이 존재하지 않습니다.")

            old_status = row[0]

            # 2. 주문 상태 업데이트
            cursor.execute(
                \"\"\"
                UPDATE Orders
                SET Status = ?,
                    ModifiedBy = ?,
                    ModifiedDate = GETDATE()
                WHERE OrderID = ?
                \"\"\",
                new_status,
                updated_by,
                order_id,
            )
            updated_count = cursor.rowcount

            # 3. 감사 로그 기록
            cursor.execute(
                \"\"\"
                INSERT INTO OrderAuditLog
                    (OrderID, OldStatus, NewStatus, ChangedBy, ChangedDate)
                VALUES (?, ?, ?, ?, GETDATE())
                \"\"\",
                order_id,
                old_status,
                new_status,
                updated_by,
            )

            # 4. 커밋
            conn.commit()

            return UpdateResult(
                updated_count=updated_count,
                success=True,
                error_message=None,
            )

        except Exception as e:
            conn.rollback()
            return UpdateResult(
                updated_count=0,
                success=False,
                error_message=str(e),
            )"""

# ──────────────────────────────────────────────
#  예시 3: 임시 테이블 + 일괄 UPDATE (커서 대신 JOIN)
# ──────────────────────────────────────────────
EXAMPLE_3_SQL = """\
CREATE PROCEDURE ProcessMonthlyReport
    @Year  INT,
    @Month INT
AS
BEGIN
    SET NOCOUNT ON;

    CREATE TABLE #MonthlySales (
        ProductID    INT,
        ProductName  NVARCHAR(200),
        TotalQty     INT,
        TotalRevenue DECIMAL(18,2)
    );

    INSERT INTO #MonthlySales (ProductID, ProductName, TotalQty, TotalRevenue)
    SELECT
        p.ProductID,
        p.ProductName,
        SUM(od.Quantity) AS TotalQty,
        SUM(od.Quantity * od.UnitPrice) AS TotalRevenue
    FROM OrderDetails od
    JOIN Orders o ON od.OrderID = o.OrderID
    JOIN Products p ON od.ProductID = p.ProductID
    WHERE YEAR(o.OrderDate) = @Year
      AND MONTH(o.OrderDate) = @Month
    GROUP BY p.ProductID, p.ProductName;

    -- 커서 대신 일괄 업데이트
    UPDATE p
    SET p.IsPopular = 1,
        p.LastPopularDate = GETDATE()
    FROM Products p
    JOIN #MonthlySales ms ON p.ProductID = ms.ProductID
    WHERE ms.TotalQty > 100;

    SELECT *
    FROM #MonthlySales
    ORDER BY TotalRevenue DESC;

    DROP TABLE #MonthlySales;
END"""

EXAMPLE_3_PYTHON = """\
import pyodbc
import pandas as pd


def process_monthly_report(
    conn_str: str,
    year: int,
    month: int,
) -> pd.DataFrame:
    \"\"\"월간 매출 리포트를 생성하고 인기 상품을 마킹합니다.\"\"\"
    with pyodbc.connect(conn_str) as conn:
        conn.autocommit = False
        cursor = conn.cursor()

        try:
            # 1. 월간 매출 집계 조회
            monthly_sales = pd.read_sql(
                \"\"\"
                SELECT
                    p.ProductID,
                    p.ProductName,
                    SUM(od.Quantity) AS TotalQty,
                    SUM(od.Quantity * od.UnitPrice) AS TotalRevenue
                FROM OrderDetails od
                JOIN Orders o ON od.OrderID = o.OrderID
                JOIN Products p ON od.ProductID = p.ProductID
                WHERE YEAR(o.OrderDate) = ? AND MONTH(o.OrderDate) = ?
                GROUP BY p.ProductID, p.ProductName
                ORDER BY TotalRevenue DESC
                \"\"\",
                conn,
                params=[year, month],
            )

            # 2. 인기 상품 일괄 업데이트
            popular_ids = monthly_sales.loc[
                monthly_sales["TotalQty"] > 100, "ProductID"
            ].tolist()

            if popular_ids:
                placeholders = ",".join("?" for _ in popular_ids)
                sql = f\"\"\"
                    UPDATE Products
                    SET IsPopular = 1,
                        LastPopularDate = GETDATE()
                    WHERE ProductID IN ({placeholders})
                \"\"\"
                cursor.execute(sql, popular_ids)

            conn.commit()
            return monthly_sales

        except Exception:
            conn.rollback()
            raise"""

# ──────────────────────────────────────────────
#  예시 4: 동적 SQL + 페이징
# ──────────────────────────────────────────────
EXAMPLE_4_SQL = """\
CREATE PROCEDURE SearchProducts
    @Keyword    NVARCHAR(100) = NULL,
    @CategoryID INT           = NULL,
    @SortBy     NVARCHAR(50)  = N'ProductName',
    @PageNum    INT           = 1,
    @PageSize   INT           = 20,
    @TotalCount INT           OUTPUT
AS
BEGIN
    SET NOCOUNT ON;

    -- 기본 검증
    IF @PageNum < 1
    BEGIN
        RAISERROR(N'@PageNum은 1 이상이어야 합니다.', 16, 1);
        RETURN;
    END

    IF @PageSize < 1
    BEGIN
        RAISERROR(N'@PageSize는 1 이상이어야 합니다.', 16, 1);
        RETURN;
    END

    -- 정렬 컬럼 화이트리스트 검증
    IF @SortBy NOT IN (N'ProductID', N'ProductName', N'Price', N'CategoryID')
    BEGIN
        RAISERROR(N'유효하지 않은 정렬 컬럼입니다.', 16, 1);
        RETURN;
    END

    -- 빈 문자열이면 NULL처럼 처리
    IF @Keyword = N''
        SET @Keyword = NULL;

    DECLARE @SQL NVARCHAR(MAX);

    -- 총 건수 조회
    SELECT @TotalCount = COUNT(*)
    FROM Products
    WHERE (@Keyword IS NULL OR ProductName LIKE N'%' + @Keyword + N'%')
      AND (@CategoryID IS NULL OR CategoryID = @CategoryID);

    -- 페이징 조회
    SET @SQL = N'
        SELECT ProductID, ProductName, Price, CategoryID
        FROM Products
        WHERE (@Keyword IS NULL OR ProductName LIKE N''%'' + @Keyword + N''%'')
          AND (@CategoryID IS NULL OR CategoryID = @CategoryID)
        ORDER BY ' + QUOTENAME(@SortBy) + N'
        OFFSET @Offset ROWS FETCH NEXT @PageSize ROWS ONLY;';

    EXEC sp_executesql
        @SQL,
        N'@Keyword NVARCHAR(100), @CategoryID INT, @Offset INT, @PageSize INT',
        @Keyword = @Keyword,
        @CategoryID = @CategoryID,
        @Offset = (@PageNum - 1) * @PageSize,
        @PageSize = @PageSize;
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
        return -(-self.total_count // self.page_size)


def search_products(
    conn_str: str,
    keyword: str | None = None,
    category_id: int | None = None,
    sort_by: str = "ProductName",
    page_num: int = 1,
    page_size: int = 20,
) -> SearchResult:
    \"\"\"상품 검색 + 총 건수 + 페이징 결과 반환\"\"\"

    # 1. 정렬 컬럼 화이트리스트 검증
    allowed_sorts = {"ProductID", "ProductName", "Price", "CategoryID"}
    if sort_by not in allowed_sorts:
        raise ValueError(
            f"sort_by는 {sorted(allowed_sorts)} 중 하나여야 합니다."
        )

    # 2. 페이지 값 검증
    if page_num < 1:
        raise ValueError("page_num은 1 이상이어야 합니다.")
    if page_size < 1:
        raise ValueError("page_size는 1 이상이어야 합니다.")

    # 3. 빈 문자열이면 None처럼 처리
    if keyword == "":
        keyword = None

    conditions: list[str] = []
    params: list[object] = []

    if keyword is not None:
        conditions.append("ProductName LIKE ?")
        params.append(f"%{keyword}%")

    if category_id is not None:
        conditions.append("CategoryID = ?")
        params.append(category_id)

    where_clause = " AND ".join(conditions) if conditions else "1=1"
    offset = (page_num - 1) * page_size

    count_sql = f\"\"\"
        SELECT COUNT(*) AS cnt
        FROM Products
        WHERE {where_clause}
    \"\"\"

    data_sql = f\"\"\"
        SELECT ProductID, ProductName, Price, CategoryID
        FROM Products
        WHERE {where_clause}
        ORDER BY {sort_by}
        OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
    \"\"\"

    with pyodbc.connect(conn_str) as conn:
        count_df = pd.read_sql(count_sql, conn, params=params)
        total_count = int(count_df.iloc[0]["cnt"])

        data_df = pd.read_sql(
            data_sql,
            conn,
            params=params + [offset, page_size],
        )

    return SearchResult(
        data=data_df,
        total_count=total_count,
        page_num=page_num,
        page_size=page_size,
    )"""

# ──────────────────────────────────────────────
#  예시 5: UPSERT (UPDATE + @@ROWCOUNT 기반 INSERT)
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

    BEGIN TRY
        BEGIN TRANSACTION;

        UPDATE Customers
        SET CustomerName = @CustomerName,
            Email        = @Email,
            Phone        = @Phone,
            ModifiedDate = GETDATE()
        WHERE CustomerID = @CustomerID;

        IF @@ROWCOUNT = 0
        BEGIN
            INSERT INTO Customers
                (CustomerID, CustomerName, Email, Phone, CreatedDate)
            VALUES
                (@CustomerID, @CustomerName, @Email, @Phone, GETDATE());
        END

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;

        DECLARE @ErrorMsg NVARCHAR(4000) = ERROR_MESSAGE();
        RAISERROR(@ErrorMsg, 16, 1);
    END CATCH
END"""

EXAMPLE_5_PYTHON = """\
import pyodbc


def upsert_customer(
    conn_str: str,
    customer_id: int,
    customer_name: str,
    email: str,
    phone: str,
) -> str:
    \"\"\"고객 정보를 UPSERT(있으면 수정, 없으면 삽입)합니다.\"\"\"
    with pyodbc.connect(conn_str) as conn:
        conn.autocommit = False
        cursor = conn.cursor()

        try:
            # 1. 먼저 업데이트 시도
            cursor.execute(
                \"\"\"
                UPDATE Customers
                SET CustomerName = ?,
                    Email = ?,
                    Phone = ?,
                    ModifiedDate = GETDATE()
                WHERE CustomerID = ?
                \"\"\",
                customer_name,
                email,
                phone,
                customer_id,
            )

            if cursor.rowcount > 0:
                conn.commit()
                return "updated"

            # 2. 업데이트된 행이 없으면 삽입
            cursor.execute(
                \"\"\"
                INSERT INTO Customers
                    (CustomerID, CustomerName, Email, Phone, CreatedDate)
                VALUES (?, ?, ?, ?, GETDATE())
                \"\"\",
                customer_id,
                customer_name,
                email,
                phone,
            )

            conn.commit()
            return "inserted"

        except Exception:
            conn.rollback()
            raise"""


# ──────────────────────────────────────────────
#  예시 6: SOFT DELETE + 삭제 이력 기록
# ──────────────────────────────────────────────
EXAMPLE_6_SQL = """\
CREATE PROCEDURE SoftDeleteProduct
    @ProductID    INT,
    @DeletedBy    NVARCHAR(100),
    @DeletedCount INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        BEGIN TRANSACTION;

        UPDATE Products
        SET IsDeleted   = 1,
            DeletedBy   = @DeletedBy,
            DeletedDate = GETDATE()
        WHERE ProductID = @ProductID
          AND IsDeleted = 0;

        SET @DeletedCount = @@ROWCOUNT;

        IF @DeletedCount = 0
        BEGIN
            RAISERROR(N'삭제 가능한 상품이 존재하지 않습니다.', 16, 1);
        END

        INSERT INTO ProductDeleteLog
            (ProductID, DeletedBy, DeletedDate)
        VALUES
            (@ProductID, @DeletedBy, GETDATE());

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;

        DECLARE @ErrorMsg NVARCHAR(4000) = ERROR_MESSAGE();
        RAISERROR(@ErrorMsg, 16, 1);
    END CATCH
END"""

EXAMPLE_6_PYTHON = """\
import pyodbc
from dataclasses import dataclass


@dataclass
class SoftDeleteResult:
    deleted_count: int
    success: bool
    error_message: str | None = None


def soft_delete_product(
    conn_str: str,
    product_id: int,
    deleted_by: str,
) -> SoftDeleteResult:
    \"\"\"상품을 soft delete 처리하고 삭제 이력을 남깁니다.\"\"\"

    with pyodbc.connect(conn_str) as conn:
        conn.autocommit = False
        cursor = conn.cursor()

        try:
            cursor.execute(
                \"\"\"
                UPDATE Products
                SET IsDeleted = 1,
                    DeletedBy = ?,
                    DeletedDate = GETDATE()
                WHERE ProductID = ?
                  AND IsDeleted = 0
                \"\"\",
                deleted_by,
                product_id,
            )
            deleted_count = cursor.rowcount

            if deleted_count == 0:
                raise ValueError("삭제 가능한 상품이 존재하지 않습니다.")

            cursor.execute(
                \"\"\"
                INSERT INTO ProductDeleteLog
                    (ProductID, DeletedBy, DeletedDate)
                VALUES (?, ?, GETDATE())
                \"\"\",
                product_id,
                deleted_by,
            )

            conn.commit()
            return SoftDeleteResult(
                deleted_count=deleted_count,
                success=True,
                error_message=None,
            )

        except Exception as e:
            conn.rollback()
            return SoftDeleteResult(
                deleted_count=0,
                success=False,
                error_message=str(e),
            )"""


# ──────────────────────────────────────────────
#  예시 7: BULK INSERT 패턴 (다건 등록)
# ──────────────────────────────────────────────
EXAMPLE_7_SQL = """\
CREATE PROCEDURE BulkInsertTags
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO Tags (TagName, CreatedDate)
    SELECT TagName, GETDATE()
    FROM StagingTags
    WHERE NOT EXISTS (
        SELECT 1
        FROM Tags t
        WHERE t.TagName = StagingTags.TagName
    );

    SELECT @@ROWCOUNT AS InsertedCount;
END"""

EXAMPLE_7_PYTHON = """\
import pyodbc
from typing import Sequence


def bulk_insert_tags(
    conn_str: str,
    tag_names: Sequence[str],
) -> int:
    \"\"\"태그 목록을 중복 제외 후 일괄 등록합니다.\"\"\"

    if not tag_names:
        return 0

    unique_tag_names = list(dict.fromkeys(tag_names))

    with pyodbc.connect(conn_str) as conn:
        conn.autocommit = False
        cursor = conn.cursor()

        try:
            cursor.fast_executemany = True

            cursor.execute("SELECT TagName FROM Tags")
            existing = {row[0] for row in cursor.fetchall()}

            rows_to_insert = [
                (tag_name,)
                for tag_name in unique_tag_names
                if tag_name not in existing
            ]

            if not rows_to_insert:
                conn.commit()
                return 0

            cursor.executemany(
                \"\"\"
                INSERT INTO Tags (TagName, CreatedDate)
                VALUES (?, GETDATE())
                \"\"\",
                rows_to_insert,
            )

            inserted_count = len(rows_to_insert)
            conn.commit()
            return inserted_count

        except Exception:
            conn.rollback()
            raise"""


# ──────────────────────────────────────────────
#  예시 8: 집계값 OUTPUT 반환
# ──────────────────────────────────────────────
EXAMPLE_8_SQL = """\
CREATE PROCEDURE GetCustomerOrderSummary
    @CustomerID     INT,
    @TotalOrders    INT OUTPUT,
    @TotalAmount    DECIMAL(18,2) OUTPUT,
    @LastOrderDate  DATETIME OUTPUT
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        @TotalOrders = COUNT(*),
        @TotalAmount = ISNULL(SUM(TotalAmount), 0),
        @LastOrderDate = MAX(OrderDate)
    FROM Orders
    WHERE CustomerID = @CustomerID;
END"""

EXAMPLE_8_PYTHON = """\
import pyodbc
from dataclasses import dataclass
from datetime import datetime


@dataclass
class CustomerOrderSummary:
    total_orders: int
    total_amount: float
    last_order_date: datetime | None


def get_customer_order_summary(
    conn_str: str,
    customer_id: int,
) -> CustomerOrderSummary:
    \"\"\"고객의 주문 집계 정보를 반환합니다.\"\"\"

    with pyodbc.connect(conn_str) as conn:
        cursor = conn.cursor()
        cursor.execute(
            \"\"\"
            SELECT
                COUNT(*) AS TotalOrders,
                ISNULL(SUM(TotalAmount), 0) AS TotalAmount,
                MAX(OrderDate) AS LastOrderDate
            FROM Orders
            WHERE CustomerID = ?
            \"\"\",
            customer_id,
        )
        row = cursor.fetchone()

    return CustomerOrderSummary(
        total_orders=int(row[0]),
        total_amount=float(row[1]),
        last_order_date=row[2],
    )"""


# ──────────────────────────────────────────────
#  예시 9: 다중 결과셋 반환
# ──────────────────────────────────────────────
EXAMPLE_9_SQL = """\
CREATE PROCEDURE GetDashboardData
    @CustomerID INT
AS
BEGIN
    SET NOCOUNT ON;

    -- 결과셋 1: 고객 기본 정보
    SELECT
        CustomerID,
        CustomerName,
        Email
    FROM Customers
    WHERE CustomerID = @CustomerID;

    -- 결과셋 2: 최근 주문 5건
    SELECT TOP (5)
        OrderID,
        OrderDate,
        TotalAmount,
        Status
    FROM Orders
    WHERE CustomerID = @CustomerID
    ORDER BY OrderDate DESC;
END"""

EXAMPLE_9_PYTHON = """\
import pyodbc
import pandas as pd
from dataclasses import dataclass


@dataclass
class DashboardData:
    customer: pd.DataFrame
    recent_orders: pd.DataFrame


def get_dashboard_data(
    conn_str: str,
    customer_id: int,
) -> DashboardData:
    \"\"\"고객 정보와 최근 주문 목록을 함께 반환합니다.\"\"\"

    with pyodbc.connect(conn_str) as conn:
        cursor = conn.cursor()
        cursor.execute(
            \"\"\"
            SELECT
                CustomerID,
                CustomerName,
                Email
            FROM Customers
            WHERE CustomerID = ?;

            SELECT TOP (5)
                OrderID,
                OrderDate,
                TotalAmount,
                Status
            FROM Orders
            WHERE CustomerID = ?
            ORDER BY OrderDate DESC;
            \"\"\",
            customer_id,
            customer_id,
        )

        customer_rows = cursor.fetchall()
        customer_columns = [col[0] for col in cursor.description]
        customer_df = pd.DataFrame.from_records(
            customer_rows,
            columns=customer_columns,
        )

        cursor.nextset()

        recent_order_rows = cursor.fetchall()
        recent_order_columns = [col[0] for col in cursor.description]
        recent_orders_df = pd.DataFrame.from_records(
            recent_order_rows,
            columns=recent_order_columns,
        )

    return DashboardData(
        customer=customer_df,
        recent_orders=recent_orders_df,
    )"""


# ──────────────────────────────────────────────
#  예시 10: CTE + ROW_NUMBER() + Top-N 조회
# ──────────────────────────────────────────────
EXAMPLE_10_SQL = """\
CREATE PROCEDURE GetTopProductsByCategory
    @CategoryID INT,
    @TopN       INT = 3
AS
BEGIN
    SET NOCOUNT ON;

    ;WITH RankedProducts AS (
        SELECT
            p.ProductID,
            p.ProductName,
            SUM(od.Quantity) AS TotalQty,
            ROW_NUMBER() OVER (
                ORDER BY SUM(od.Quantity) DESC, p.ProductName ASC
            ) AS RowNum
        FROM Products p
        JOIN OrderDetails od ON p.ProductID = od.ProductID
        WHERE p.CategoryID = @CategoryID
        GROUP BY p.ProductID, p.ProductName
    )
    SELECT
        ProductID,
        ProductName,
        TotalQty
    FROM RankedProducts
    WHERE RowNum <= @TopN
    ORDER BY RowNum;
END"""

EXAMPLE_10_PYTHON = """\
import pyodbc
import pandas as pd


def get_top_products_by_category(
    conn_str: str,
    category_id: int,
    top_n: int = 3,
) -> pd.DataFrame:
    \"\"\"카테고리별 판매량 상위 상품을 조회합니다.\"\"\"

    query = \"\"\"
        WITH RankedProducts AS (
            SELECT
                p.ProductID,
                p.ProductName,
                SUM(od.Quantity) AS TotalQty,
                ROW_NUMBER() OVER (
                    ORDER BY SUM(od.Quantity) DESC, p.ProductName ASC
                ) AS RowNum
            FROM Products p
            JOIN OrderDetails od ON p.ProductID = od.ProductID
            WHERE p.CategoryID = ?
            GROUP BY p.ProductID, p.ProductName
        )
        SELECT
            ProductID,
            ProductName,
            TotalQty
        FROM RankedProducts
        WHERE RowNum <= ?
        ORDER BY RowNum
    \"\"\"

    with pyodbc.connect(conn_str) as conn:
        df = pd.read_sql(query, conn, params=[category_id, top_n])

    return df"""


# ──────────────────────────────────────────────
#  전체 예시 리스트
# ──────────────────────────────────────────────
ALL_EXAMPLES = [
    {"tag": "simple_select",      "sql": EXAMPLE_1_SQL,  "python": EXAMPLE_1_PYTHON},
    {"tag": "transaction",        "sql": EXAMPLE_2_SQL,  "python": EXAMPLE_2_PYTHON},
    {"tag": "temp_table",         "sql": EXAMPLE_3_SQL,  "python": EXAMPLE_3_PYTHON},
    {"tag": "dynamic_sql",        "sql": EXAMPLE_4_SQL,  "python": EXAMPLE_4_PYTHON},
    {"tag": "merge_upsert",       "sql": EXAMPLE_5_SQL,  "python": EXAMPLE_5_PYTHON},
    {"tag": "soft_delete",        "sql": EXAMPLE_6_SQL,  "python": EXAMPLE_6_PYTHON},
    {"tag": "bulk_insert",        "sql": EXAMPLE_7_SQL,  "python": EXAMPLE_7_PYTHON},
    {"tag": "scalar_aggregate",   "sql": EXAMPLE_8_SQL,  "python": EXAMPLE_8_PYTHON},
    {"tag": "multiple_resultset", "sql": EXAMPLE_9_SQL,  "python": EXAMPLE_9_PYTHON},
    {"tag": "cte_ranking",        "sql": EXAMPLE_10_SQL, "python": EXAMPLE_10_PYTHON},
]
