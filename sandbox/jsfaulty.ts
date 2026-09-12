// Basic TypeScript code
function getDiscountedPrice(price: number, discount: number): number {
    if (discount < 0 || discount > 1) {
        return -1;
    }

    const discountAmount = price * discount; 
    
    return price - discountAmount;
}

console.log("The final price is: ", getDiscountedPrice(100, 0.2))