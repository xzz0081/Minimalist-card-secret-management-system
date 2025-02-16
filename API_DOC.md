# 卡密系统 API 文档

## API 基本信息

- 基础URL: `http://localhost:5000`
- 响应格式: JSON
- 编码方式: UTF-8
- 设备限制: 每个卡密仅限一个设备使用

## API 接口列表

### 1. 验证卡密

验证卡密的有效性并返回剩余时间。系统会自动识别设备标识，同一个卡密只能在首次使用的设备上继续使用。

**接口地址**
```
GET /api/verify_card/<card_key>
```

**请求参数**

| 参数位置 | 参数名 | 类型 | 必填 | 说明 |
|---------|--------|------|------|------|
| URL路径 | card_key | string | 是 | 要验证的卡密 |

**请求头**
```
Accept: application/json
User-Agent: [客户端标识]  // 用于设备识别，必须保持一致
```

**请求示例**
```bash
# 使用 curl
curl -X GET "http://localhost:5000/api/verify_card/your_card_key" \
     -H "Accept: application/json" \
     -H "User-Agent: YourApp/1.0"

# 使用 Python requests
import requests

response = requests.get(
    "http://localhost:5000/api/verify_card/your_card_key",
    headers={
        "Accept": "application/json",
        "User-Agent": "YourApp/1.0"
    }
)
```

**响应参数**

| 参数名 | 类型 | 说明 |
|--------|------|------|
| valid | boolean | 卡密是否有效 |
| remaining_minutes | integer | 剩余有效分钟数 |
| message | string | 状态说明信息 |

**响应示例**

```json
// 成功响应 - 未使用的卡密
{
    "valid": true,
    "remaining_minutes": 60,
    "message": "卡密首次使用成功"
}

// 成功响应 - 已使用但未过期的卡密（同一设备）
{
    "valid": true,
    "remaining_minutes": 30,
    "message": "卡密有效"
}

// 失败响应 - 不同设备使用
{
    "valid": false,
    "message": "该卡密已被其他设备使用"
}

// 失败响应 - 卡密不存在
{
    "valid": false,
    "message": "卡密不存在"
}

// 失败响应 - 卡密已过期
{
    "valid": false,
    "remaining_minutes": 0,
    "message": "卡密已过期"
}
```

**状态码说明**

| 状态码 | 说明 |
|--------|------|
| 200 | 请求成功 |
| 403 | 设备限制（已被其他设备使用） |
| 404 | 卡密不存在 |
| 429 | 请求频率超限 |
| 500 | 服务器内部错误 |

## 开发示例

### Python 示例
```python
import requests

def verify_card(card_key):
    url = f"http://localhost:5000/api/verify_card/{card_key}"
    headers = {
        "Accept": "application/json",
        "User-Agent": "YourApp/1.0"  # 设备标识，必须保持一致
    }
    
    try:
        response = requests.get(url, headers=headers)
        
        if response.status_code == 403:
            print("该卡密已被其他设备使用")
            return False
            
        response.raise_for_status()
        
        data = response.json()
        if data["valid"]:
            print(f"卡密验证成功！剩余时间：{data['remaining_minutes']}分钟")
            return True
        else:
            print(f"卡密验证失败：{data['message']}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"请求失败：{str(e)}")
        return False

# 使用示例
card_key = "your_card_key"
verify_card(card_key)
```

### JavaScript 示例
```javascript
async function verifyCard(cardKey) {
    try {
        const response = await fetch(`http://localhost:5000/api/verify_card/${cardKey}`, {
            method: 'GET',
            headers: {
                'Accept': 'application/json'
            }
        });
        
        const data = await response.json();
        
        if (data.valid) {
            console.log(`卡密验证成功！剩余时间：${data.remaining_minutes}分钟`);
            return true;
        } else {
            console.log(`卡密验证失败：${data.message}`);
            return false;
        }
    } catch (error) {
        console.error('请求失败：', error);
        return false;
    }
}

// 使用示例
const cardKey = 'your_card_key';
verifyCard(cardKey);
```

### PHP 示例
```php
function verifyCard($cardKey) {
    $url = "http://localhost:5000/api/verify_card/" . $cardKey;
    
    $options = [
        'http' => [
            'header' => "Accept: application/json\r\n",
            'method' => 'GET'
        ]
    ];
    
    $context = stream_context_create($options);
    
    try {
        $response = file_get_contents($url, false, $context);
        $data = json_decode($response, true);
        
        if ($data['valid']) {
            echo "卡密验证成功！剩余时间：" . $data['remaining_minutes'] . "分钟\n";
            return true;
        } else {
            echo "卡密验证失败：" . $data['message'] . "\n";
            return false;
        }
    } catch (Exception $e) {
        echo "请求失败：" . $e->getMessage() . "\n";
        return false;
    }
}

// 使用示例
$cardKey = 'your_card_key';
verifyCard($cardKey);
```

## 注意事项

1. **设备识别**
   - 系统通过请求头中的User-Agent和客户端IP识别设备
   - 确保在同一设备上使用时保持User-Agent一致
   - 更换设备或重置设备标识将无法使用已激活的卡密

2. **时间处理**
   - 系统使用UTC时间
   - 请在客户端处理好时区转换
   - 剩余时间精确到分钟

3. **错误处理**
   - 建议实现请求重试机制
   - 添加超时处理
   - 处理网络异常情况

4. **安全建议**
   - 在生产环境中使用HTTPS
   - 添加适当的请求频率限制
   - 考虑添加API认证机制
   - 避免设备标识被篡改

5. **最佳实践**
   - 缓存验证结果，避免频繁请求
   - 实现错误重试机制
   - 添加日志记录
   - 监控API调用情况
   - 保存设备标识信息

## 更新日志

### v1.2.0 (2024-02-18)
- 优化卡密状态显示
- 添加实时倒计时功能
- 增加剩余时间的精确显示（时分秒）
- 改进过期状态判断逻辑

### v1.1.0 (2024-02-17)
- 添加设备限制功能
- 增加设备识别机制
- 新增403状态码处理

### v1.0.0 (2024-02-17)
- 初始版本发布
- 基本卡密验证功能
- 时间限制功能

## 状态说明

卡密可能存在以下几种状态：

1. **未使用**
   - 卡密尚未被激活
   - `valid` 为 true
   - `remaining_minutes` 为初始设置时间

2. **使用中**
   - 卡密已激活且未过期
   - `valid` 为 true
   - `remaining_minutes` 为实时剩余分钟数
   - 支持精确到秒的倒计时显示

3. **已过期**
   - 卡密已超过有效期
   - `valid` 为 false
   - `remaining_minutes` 为 0

4. **设备冲突**
   - 卡密被其他设备使用
   - `valid` 为 false
   - 返回403状态码

## 客户端建议

1. **倒计时显示**
   - 建议在客户端实现实时倒计时显示
   - 可参考以下JavaScript代码实现倒计时：

```javascript
function updateCountdown(expirationTime) {
    const now = new Date();
    const expiration = new Date(expirationTime);
    
    if (now >= expiration) {
        return '已过期';
    }
    
    const remainingTime = expiration - now;
    const hours = Math.floor(remainingTime / (1000 * 60 * 60));
    const minutes = Math.floor((remainingTime % (1000 * 60 * 60)) / (1000 * 60));
    const seconds = Math.floor((remainingTime % (1000 * 60)) / 1000);
    
    return `${hours}时${minutes}分${seconds}秒`;
}

// 使用示例
setInterval(() => {
    const countdown = updateCountdown(expirationTime);
    document.getElementById('countdown').textContent = countdown;
}, 1000);
```

2. **状态更新**
   - 定期检查卡密状态（建议30秒-1分钟间隔）
   - 实现优雅的过期处理
   - 注意处理设备识别相关的错误 